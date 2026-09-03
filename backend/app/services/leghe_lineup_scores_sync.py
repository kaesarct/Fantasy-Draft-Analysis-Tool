"""Sync punteggi di giornata da leghe.fantacalcio.it via gaming/v1/teamLineup.

A differenza dell'Excel "Calendario" (leghe_results_sync.py), che risponde
"File non disponibile" per le competizioni senza scontri diretti, il campo
"tot" della risposta teamLineup da' il punteggio totale di una squadra per
una giornata senza bisogno di un avversario — funziona anche per Silver.
Verificato dal vivo su Tenkaichi (non tracciata da noi, usata solo per
confermare il formato): punteggi reali coerenti con "points" (il piazzamento
stile F1) 1..N per le squadre partecipanti a quella giornata."""
from sqlalchemy.orm import Session

from app.models.competition import Competition, CompetitionMatchdayScore
from app.models.fanta_team import FantaTeam
from app.models.season import Season
from app.services.fanta_client import fanta_client
from app.services.leghe_client import LegheClient
from app.services.leghe_competition_sync import ensure_competitions


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

    for comp in query.all():
        comp_type = comp.type.value if hasattr(comp.type, "value") else comp.type
        leghe_comp = leghe_comps.get(comp.leghe_id)
        if not leghe_comp:
            report[comp_type] = {"error": "competizione non trovata su leghe.fantacalcio.it"}
            continue

        s_day, e_day = leghe_comp["sDay"], leghe_comp["eDay"]
        upper = min(e_day, last_matchday)
        if upper < s_day:
            report[comp_type] = {"scores_synced": 0, "teams_unmatched": 0}
            continue

        our_teams = {
            t.leghe_team_id: t
            for t in db.query(FantaTeam).filter(
                FantaTeam.season_id == season.id, FantaTeam.leghe_team_id.isnot(None)
            )
        }
        leghe_team_ids = leghe_comp.get("tmids") or []
        unmatched = [tid for tid in leghe_team_ids if tid not in our_teams]

        already_synced = {
            (row.fanta_team_id, row.match_day)
            for row in db.query(CompetitionMatchdayScore).filter(
                CompetitionMatchdayScore.competition_id == comp.id
            )
        }

        synced = 0
        for match_day in range(s_day, upper + 1):
            # Rilanci ripetuti non ri-scaricano giornate gia' sincronizzate,
            # tranne l'ultima (puo' avere correzioni tardive dei voti).
            refresh = match_day == upper
            for leghe_team_id in leghe_team_ids:
                team = our_teams.get(leghe_team_id)
                if not team:
                    continue
                if not refresh and (team.id, match_day) in already_synced:
                    continue

                data = client.get_team_lineup(comp.leghe_id, match_day, leghe_team_id)
                if not data or data.get("tot") is None:
                    continue

                existing = db.query(CompetitionMatchdayScore).filter(
                    CompetitionMatchdayScore.competition_id == comp.id,
                    CompetitionMatchdayScore.fanta_team_id == team.id,
                    CompetitionMatchdayScore.match_day == match_day,
                ).first()
                if existing:
                    existing.score = data["tot"]
                else:
                    db.add(CompetitionMatchdayScore(
                        competition_id=comp.id, fanta_team_id=team.id,
                        match_day=match_day, score=data["tot"],
                    ))
                synced += 1

        db.commit()
        report[comp_type] = {
            "scores_synced": synced, "teams_unmatched": len(unmatched),
            "appena_creata": comp_type in newly_created,
        }

    return report
