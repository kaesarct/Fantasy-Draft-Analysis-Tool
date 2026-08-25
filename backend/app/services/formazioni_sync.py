"""Sync formazioni da leghe.fantacalcio.it → LineupSubmission/LineupPlayer.

Ogni squadra arriva come {"mdl": modulo, "starts": [...], "bench": [...]},
ogni giocatore come {"pid": fanta_id, ...}: risoluzione diretta per fanta_id,
niente piu' matching per nome/ruolo (la vecchia struttura JSON, senza id
numerici, non esiste piu' lato leghe.fantacalcio.it). Il payload grezzo viene
comunque conservato in LineupRawImport per audit e riprocessamento. Team e
giocatori non riconosciuti non fanno fallire il sync: finiscono nel report.
"""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.competition import Competition
from app.models.fanta_team import FantaTeam
from app.models.lineup import LineupSubmission, LineupPlayer
from app.models.lineup_import import LineupRawImport
from app.models.player import Player
from app.services.fanta_client import fanta_client
from app.services.leghe_client import LegheClient

import logging
logger = logging.getLogger(__name__)

_MAX_REPORTED_NAMES = 20


def _normalize(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name.strip().lower()).strip("_")


def _resolve_competition(db: Session, season_id: int, leghe_id: int, slug: str) -> Competition | None:
    comp = (
        db.query(Competition)
        .filter(Competition.season_id == season_id, Competition.leghe_id == leghe_id)
        .first()
    )
    if comp:
        return comp

    # Primo sync: aggancio per nome normalizzato o per tipo, poi memorizzo leghe_id.
    slug_norm = _normalize(slug)
    for candidate in db.query(Competition).filter(Competition.season_id == season_id).all():
        name_norm = _normalize(candidate.name)
        type_norm = candidate.type.value.lower()
        if slug_norm in name_norm or name_norm in slug_norm or type_norm in slug_norm:
            candidate.leghe_id = leghe_id
            return candidate
    return None


def _save_raw(db: Session, leghe_id: int, slug: str, match_day: int, data) -> None:
    raw_json = json.dumps(data, ensure_ascii=False)
    record = (
        db.query(LineupRawImport)
        .filter(
            LineupRawImport.leghe_competition_id == leghe_id,
            LineupRawImport.match_day == match_day,
        )
        .first()
    )
    if record:
        record.competition_name = slug
        record.raw_json = raw_json
        record.fetched_at = datetime.utcnow()
    else:
        db.add(
            LineupRawImport(
                leghe_competition_id=leghe_id,
                competition_name=slug,
                match_day=match_day,
                raw_json=raw_json,
            )
        )


def _import_competition_lineups(db: Session, comp: Competition, match_day: int, data: dict) -> dict:
    """Mappa {nome_squadra: {"mdl", "starts", "bench"}} su LineupSubmission/LineupPlayer."""
    teams = {
        _normalize(t.name): t
        for t in db.query(FantaTeam).filter(FantaTeam.season_id == comp.season_id).all()
    }
    players_by_fanta_id = {
        p.fanta_id: p for p in db.query(Player).filter(Player.fanta_id.isnot(None)).all()
    }

    unmatched_teams: set[str] = set()
    unmatched_players: set[str] = set()
    imported_players = 0
    lineups = 0

    for team_name, lineup_data in data.items():
        team = teams.get(_normalize(team_name))
        if not team:
            unmatched_teams.add(team_name)
            continue

        lineup = (
            db.query(LineupSubmission)
            .filter(
                LineupSubmission.fanta_team_id == team.id,
                LineupSubmission.competition_id == comp.id,
                LineupSubmission.match_day == match_day,
            )
            .first()
        )
        if not lineup:
            lineup = LineupSubmission(
                fanta_team_id=team.id, competition_id=comp.id, match_day=match_day
            )
            db.add(lineup)
            db.flush()

        mdl = lineup_data.get("mdl")
        lineup.module = int(mdl) if mdl else None
        lineup.submitted_at = datetime.utcnow()
        lineups += 1

        # Senza chiave naturale per riga, delete+reinsert e' l'unico upsert corretto.
        db.query(LineupPlayer).filter(LineupPlayer.lineup_id == lineup.id).delete()

        bench_order = 0
        for is_starter, entries in (
            (True, lineup_data.get("starts") or []),
            (False, lineup_data.get("bench") or []),
        ):
            for entry in entries:
                pid = entry.get("pid")
                player = players_by_fanta_id.get(pid)
                if not player:
                    unmatched_players.add(str(pid))
                    continue
                db.add(
                    LineupPlayer(
                        lineup_id=lineup.id,
                        player_id=player.id,
                        is_starter=is_starter,
                        bench_order=None if is_starter else bench_order,
                    )
                )
                if not is_starter:
                    bench_order += 1
                imported_players += 1

    return {
        "lineups": lineups,
        "players_imported": imported_players,
        "unmatched_teams": sorted(unmatched_teams)[:_MAX_REPORTED_NAMES],
        "unmatched_players": sorted(unmatched_players)[:_MAX_REPORTED_NAMES],
        "unmatched_players_count": len(unmatched_players),
    }


# ── Orchestrazione ──────────────────────────────────────────────────────


def sync_formazioni(db: Session, season_id: int, match_day: int | None = None) -> dict:
    """Fetch di tutte le formazioni da leghe.fantacalcio.it e import strutturato.
    Di default sincronizza la giornata successiva all'ultima conclusa (quella
    per cui le formazioni sono rilevanti da controllare, non quella gia' giocata)."""
    day = match_day if match_day is not None else fanta_client.get_last_matchday() + 1

    client = LegheClient()
    client.login()
    risultati = client.get_tutte_le_formazioni(day)

    report = {}
    for slug, risultato in risultati.items():
        if risultato is None:
            report[slug] = {
                "ok": False,
                "match_day": day,
                "message": f"Nessuna formazione disponibile per la giornata {day}",
            }
            continue

        leghe_id = risultato["id_comp"]
        comp_match_day = risultato["giornata"]
        entry = {"ok": True, "match_day": comp_match_day, "raw_saved": True}

        try:
            _save_raw(db, leghe_id, slug, comp_match_day, risultato["dati"])
        except Exception as e:
            logger.error("Errore salvataggio raw per '%s': %s", slug, e)
            entry.update(ok=False, raw_saved=False, message="Errore nel salvataggio del raw")
            report[slug] = entry
            continue

        comp = _resolve_competition(db, season_id, leghe_id, slug)
        if not comp:
            entry["message"] = (
                "Competizione non mappata: nessuna Competition corrispondente "
                f"per la stagione {season_id} (raw comunque salvato)"
            )
            report[slug] = entry
            continue

        try:
            entry.update(competition_id=comp.id, **_import_competition_lineups(
                db, comp, comp_match_day, risultato["dati"]
            ))
        except Exception as e:
            # Il raw e' gia' in sessione: il parsing fallito non fa fallire il sync.
            logger.error("Errore import formazioni per '%s': %s", slug, e)
            entry.update(ok=False, message="Parsing non riuscito (struttura da analizzare)")
        report[slug] = entry

    db.commit()
    return {"ok": True, "competitions": report}
