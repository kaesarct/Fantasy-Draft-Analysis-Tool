"""Sync punteggi di giornata da leghe.fantacalcio.it via onboarding/v1/league/competition/calendar
e gaming/v1/teamLineup.

Il calendario REST su apileague.fantacalcio.it espone per ogni giornata calcolata
i punteggi ufficiali (ptH / ptA) di tutte le squadre partecipanti — inclusa Silver
(dove ogni squadra ha una riga con tIdH=team_id, tIdA=0 e ptH=tot). Se per una
squadra il punteggio non e' presente nel calendario ma la giornata risulta attiva,
ripiega su get_team_lineup risolvendo automaticamente il turno di competizione."""
from sqlalchemy.orm import Session

from app.models.competition import Competition, CompetitionMatchdayScore
from app.models.fanta_team import FantaTeam
from app.models.season import Season
from app.services.fanta_client import fanta_client
from app.services.leghe_client import LegheClient
from app.services.leghe_competition_sync import ensure_competitions


def _zero_reason(last_matchday, s_day, e_day, n_teams, n_unmatched, skipped_cached, empty) -> str:
    if n_teams == n_unmatched:
        return "nessuna squadra della competizione e' collegata (leghe_team_id mancante)"
    if skipped_cached and not empty:
        return "giornate gia' sincronizzate in precedenza, nulla di nuovo"
    return (f"{empty} lineup non disponibili (giornata non attiva o senza punteggio); "
            f"ultima giornata Serie A={last_matchday}, competizione giornate {s_day}-{e_day}")


def sync_matchday_scores(db: Session, season: Season, comp_types: list[str] | None = None) -> dict:
    client = LegheClient()
    client.login()
    last_matchday = fanta_client.get_last_matchday()

    all_leghe_comps = client.list_competitions()
    leghe_comps = {c["id"]: c for c in all_leghe_comps}

    # Crea (se mancano) e aggancia tutte le competizioni note trovate su
    # leghe.fantacalcio.it — cosi' una comparsa a stagione in corso (es. UEFA
    # a fine gironi Ciempions) viene sincronizzata gia' in questo stesso giro,
    # senza dover passare prima da "Carica da leghe.fantacalcio.it".
    ensured = ensure_competitions(db, season, all_leghe_comps)
    newly_created = set(ensured["created"])
    report = {}

    query = db.query(Competition).filter(
        Competition.season_id == season.id, Competition.leghe_id.isnot(None)
    )
    if comp_types:
        query = query.filter(Competition.type.in_(comp_types))

    our_teams = {
        t.leghe_team_id: t
        for t in db.query(FantaTeam).filter(
            FantaTeam.season_id == season.id, FantaTeam.leghe_team_id.isnot(None)
        )
    }

    for comp in query.all():
        comp_type = comp.type.value if hasattr(comp.type, "value") else comp.type
        leghe_comp = leghe_comps.get(comp.leghe_id)
        if not leghe_comp:
            report[comp_type] = {"error": "competizione non trovata su leghe.fantacalcio.it"}
            continue

        s_day, e_day = leghe_comp["sDay"], leghe_comp["eDay"]
        leghe_team_ids = leghe_comp.get("tmids") or []
        unmatched = [tid for tid in leghe_team_ids if tid not in our_teams]

        existing_rows = {
            (row.fanta_team_id, row.match_day): row
            for row in db.query(CompetitionMatchdayScore).filter(
                CompetitionMatchdayScore.competition_id == comp.id
            )
        }

        calendar = client.get_competition_calendar(comp.leghe_id)
        synced = skipped_cached = empty = 0

        if calendar:
            calc_days = [d for d in calendar if d.get("calculated")]
            max_calc_day = max((int(d.get("championshipMatchDay", 0)) for d in calc_days), default=0)

            for day_entry in calendar:
                if not day_entry.get("calculated"):
                    continue
                comp_round = int(day_entry.get("matchDay", 1))
                serie_a_day = int(day_entry.get("championshipMatchDay", comp_round))
                refresh = (serie_a_day == max_calc_day)

                scores_by_tid: dict[int, float] = {}
                for m in day_entry.get("matches") or []:
                    h_id = m.get("tIdH")
                    a_id = m.get("tIdA")
                    pt_h = m.get("ptH")
                    pt_a = m.get("ptA")
                    if h_id and pt_h is not None and float(pt_h) > 0:
                        scores_by_tid[int(h_id)] = float(pt_h)
                    if a_id and pt_a is not None and float(pt_a) > 0:
                        scores_by_tid[int(a_id)] = float(pt_a)

                target_tids = leghe_team_ids or list(scores_by_tid.keys())
                for leghe_team_id in target_tids:
                    team = our_teams.get(leghe_team_id)
                    if not team:
                        continue
                    existing = existing_rows.get((team.id, serie_a_day))
                    if existing and not refresh:
                        skipped_cached += 1
                        continue

                    score_val = scores_by_tid.get(leghe_team_id)
                    if score_val is None:
                        data = client.get_team_lineup(
                            comp.leghe_id, serie_a_day, leghe_team_id, comp_round=comp_round
                        )
                        if data and data.get("tot") is not None:
                            score_val = float(data["tot"])

                    if score_val is None:
                        empty += 1
                        continue

                    if existing:
                        existing.score = score_val
                    else:
                        new_row = CompetitionMatchdayScore(
                            competition_id=comp.id,
                            fanta_team_id=team.id,
                            match_day=serie_a_day,
                            score=score_val,
                        )
                        db.add(new_row)
                        existing_rows[(team.id, serie_a_day)] = new_row
                    synced += 1
        else:
            upper = min(e_day, last_matchday)
            if upper < s_day:
                report[comp_type] = {
                    "scores_synced": 0, "teams_unmatched": 0,
                    "reason": f"nessuna giornata da scaricare: ultima giornata Serie A={last_matchday}, "
                              f"competizione giornate {s_day}-{e_day}",
                }
                continue

            for match_day in range(s_day, upper + 1):
                refresh = match_day == upper
                for leghe_team_id in leghe_team_ids:
                    team = our_teams.get(leghe_team_id)
                    if not team:
                        continue
                    existing = existing_rows.get((team.id, match_day))
                    if existing and not refresh:
                        skipped_cached += 1
                        continue

                    data = client.get_team_lineup(comp.leghe_id, match_day, leghe_team_id)
                    if not data or data.get("tot") is None:
                        empty += 1
                        continue

                    if existing:
                        existing.score = float(data["tot"])
                    else:
                        new_row = CompetitionMatchdayScore(
                            competition_id=comp.id,
                            fanta_team_id=team.id,
                            match_day=match_day,
                            score=float(data["tot"]),
                        )
                        db.add(new_row)
                        existing_rows[(team.id, match_day)] = new_row
                    synced += 1

        db.commit()
        report[comp_type] = {
            "scores_synced": synced, "teams_unmatched": len(unmatched),
            "appena_creata": comp_type in newly_created,
            "reason": None if synced else _zero_reason(
                last_matchday, s_day, e_day, len(leghe_team_ids), len(unmatched), skipped_cached, empty
            ),
        }

    return report
