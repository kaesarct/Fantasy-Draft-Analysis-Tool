"""Import calendario/risultati da leghe.fantacalcio.it in MatchResult.

Sostituisce, competizione per competizione, il ripiego di awards.py basato su
CompetitionStanding con dati reali: stesso formato Excel gia' interpretato da
etl/import_history.py per lo storico (regex duplicate qui, non importate — 4
righe stabili, evita di far dipendere app/ da uno script one-off in etl/)."""
import io
import re

import pandas as pd
from sqlalchemy.orm import Session

from app.models.competition import Competition, CompetitionPhase, MatchResult
from app.models.fanta_team import FantaTeam
from app.models.season import Season
from app.services.leghe_client import LegheClient

GIORNATA_RE = re.compile(r"(\d+)ª\s+Giornata\s+lega", re.IGNORECASE)
GOALS_RE = re.compile(r"^(\d+)\s*-\s*(\d+)$")
GIRONE_LETTER_RE = re.compile(r"^[A-Z]$")


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _phase_from_label(text: str) -> CompetitionPhase | None:
    s = text.strip().casefold()
    if "giron" in s:
        return CompetitionPhase.GROUP
    if "ottavi" in s:
        return CompetitionPhase.ROUND_OF_16
    if "quart" in s:
        return CompetitionPhase.QUARTER_FINAL
    if "semifinal" in s:
        return CompetitionPhase.SEMI_FINAL
    if "finale" in s:
        return CompetitionPhase.FINAL
    return None


def _parse_block(df, start: int, col: int, match_day: int, phase: CompetitionPhase) -> list[dict]:
    """Partite di un singolo blocco 'Nª Giornata lega'. Nessuna scrittura DB:
    funzione pura, cosi' e' testabile senza sessione."""
    matches = []
    for idx in range(start, len(df)):
        home = df.iat[idx, col]
        if _is_blank(home) or (isinstance(home, str) and GIORNATA_RE.search(home)):
            break
        shift = 1 if isinstance(home, str) and GIRONE_LETTER_RE.match(home.strip()) else 0
        if col + shift + 4 >= df.shape[1]:
            break
        home = df.iat[idx, col + shift]
        away = df.iat[idx, col + shift + 3]
        goals = df.iat[idx, col + shift + 4]
        if _is_blank(home) or _is_blank(away):
            break

        goals_match = GOALS_RE.match(str(goals).strip()) if not _is_blank(goals) else None
        if not goals_match:
            # Nessun punteggio "N-M": giornata non ancora giocata (il caso
            # normale scaricando durante la stagione) — non un vero 0-0.
            continue

        score_home = None if _is_blank(df.iat[idx, col + shift + 1]) else float(df.iat[idx, col + shift + 1])
        score_away = None if _is_blank(df.iat[idx, col + shift + 2]) else float(df.iat[idx, col + shift + 2])
        matches.append({
            "match_day": match_day, "phase": phase,
            "home_name": str(home).strip(), "away_name": str(away).strip(),
            "score_home": score_home, "score_away": score_away,
            "goals_home": int(goals_match.group(1)), "goals_away": int(goals_match.group(2)),
        })
    return matches


def parse_calendar_excel(excel_bytes: bytes, is_cup: bool) -> list[dict]:
    """Tutte le partite gia' giocate in un Excel 'Calendario' di
    leghe.fantacalcio.it. `is_cup` decide la fase di default (GROUP per le
    coppe, REGULAR per i campionati a girone unico) prima del primo eventuale
    cambio fase rilevato nel file."""
    df = pd.read_excel(io.BytesIO(excel_bytes), header=None)
    matches = []
    current_phase = CompetitionPhase.GROUP if is_cup else CompetitionPhase.REGULAR
    for idx in range(len(df)):
        first = df.iat[idx, 0]
        if isinstance(first, str) and not GIORNATA_RE.search(first):
            label_phase = _phase_from_label(first)
            if label_phase:
                current_phase = label_phase
        for col in range(df.shape[1]):
            cell = df.iat[idx, col]
            if not isinstance(cell, str):
                continue
            match = GIORNATA_RE.search(cell)
            if not match:
                continue
            match_day = int(match.group(1))
            matches.extend(_parse_block(df, idx + 1, col, match_day, current_phase))
    return matches


def sync_results(db: Session, season: Season, comp_types: list[str] | None = None) -> dict:
    client = LegheClient()
    client.login()

    query = db.query(Competition).filter(
        Competition.season_id == season.id, Competition.leghe_id.isnot(None)
    )
    if comp_types:
        query = query.filter(Competition.type.in_(comp_types))

    report = {}
    for comp in query.all():
        comp_type = comp.type.value if hasattr(comp.type, "value") else comp.type
        try:
            teams_by_leghe_id = client.list_competition_teams(comp.leghe_id)
            our_teams = {
                t.leghe_team_id: t
                for t in db.query(FantaTeam).filter(
                    FantaTeam.season_id == season.id, FantaTeam.leghe_team_id.isnot(None)
                )
            }
            name_to_team = {
                name: our_teams[leghe_team_id]
                for leghe_team_id, name in teams_by_leghe_id.items()
                if leghe_team_id in our_teams
            }

            is_cup = comp_type not in {"GOLD", "BRONZE", "CARBON", "SILVER"}
            excel_bytes = client.download_results_excel(comp.leghe_id, comp_type)
            matches = parse_calendar_excel(excel_bytes, is_cup)

            imported = updated = 0
            unmatched: set[str] = set()
            for m in matches:
                home_team = name_to_team.get(m["home_name"])
                away_team = name_to_team.get(m["away_name"])
                if not home_team:
                    unmatched.add(m["home_name"])
                if not away_team:
                    unmatched.add(m["away_name"])
                if not home_team or not away_team:
                    continue

                existing = db.query(MatchResult).filter(
                    MatchResult.competition_id == comp.id,
                    MatchResult.match_day == m["match_day"],
                    MatchResult.fanta_team_home_id == home_team.id,
                    MatchResult.fanta_team_away_id == away_team.id,
                ).first()
                values = dict(
                    score_home=m["score_home"], score_away=m["score_away"],
                    goals_home=m["goals_home"], goals_away=m["goals_away"],
                    phase=m["phase"],
                )
                if existing:
                    for k, v in values.items():
                        setattr(existing, k, v)
                    updated += 1
                else:
                    db.add(MatchResult(
                        competition_id=comp.id, match_day=m["match_day"],
                        fanta_team_home_id=home_team.id, fanta_team_away_id=away_team.id,
                        **values,
                    ))
                    imported += 1

            db.commit()
            report[comp_type] = {
                "matches_imported": imported, "matches_updated": updated,
                "teams_unmatched": sorted(unmatched),
            }
        except Exception as e:
            db.rollback()
            report[comp_type] = {"error": str(e)}

    return report
