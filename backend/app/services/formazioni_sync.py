"""Sync formazioni da leghe.fantacalcio.it → LineupSubmission/LineupPlayer.

Il JSON delle formazioni non ha una struttura consolidata: l'estrazione delle
righe giocatore e' best-effort (chiavi candidate case-insensitive, ricorsione
limitata) e il payload grezzo viene sempre conservato in LineupRawImport per
audit e riprocessamento. Team e giocatori non riconosciuti non fanno fallire
il sync: finiscono nel report.
"""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.competition import Competition
from app.models.fanta_team import FantaTeam
from app.models.lineup import LineupSubmission, LineupPlayer
from app.models.lineup_import import LineupRawImport
from app.models.player import Player
from app.services.leghe_client import LegheClient

import logging
logger = logging.getLogger(__name__)

_MAX_DEPTH = 15
_MAX_REPORTED_NAMES = 20

_NAME_KEYS = ("nome", "n", "cognome", "playername", "nomegiocatore", "player_name")
_ROLE_KEYS = ("r", "ruolo", "role")
_TEAM_KEYS = ("squadra", "team", "sq", "squadra_reale")
_FANTATEAM_KEYS = ("nomesquadra", "squadra", "teamname", "nome_squadra")
_STARTER_KEYS = ("t", "titolare", "starter", "st", "panchina")


# ── Estrazione best-effort dal JSON (logica portata dal bot) ────────────


def _get_ci(d, keys):
    """Primo valore non nullo tra le chiavi candidate, case-insensitive."""
    lowered = {str(k).lower(): v for k, v in d.items()}
    for key in keys:
        value = lowered.get(key)
        if value is not None:
            return value
    return None


def _is_player_dict(d):
    # Doppia condizione (nome + ruolo) per ridurre i falsi positivi:
    # la struttura del JSON e' ignota.
    return _get_ci(d, _NAME_KEYS) is not None and _get_ci(d, _ROLE_KEYS) is not None


def _iter_player_dicts(node, fantateam=None, depth=0):
    """Generatore ricorsivo su dict/list annidati. Yield (player_dict, fantateam)."""
    if depth > _MAX_DEPTH:
        return
    if isinstance(node, dict):
        if _is_player_dict(node):
            yield node, fantateam
            return
        team_name = _get_ci(node, _FANTATEAM_KEYS)
        if isinstance(team_name, str):
            fantateam = team_name
        for value in node.values():
            yield from _iter_player_dicts(value, fantateam, depth + 1)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_player_dicts(item, fantateam, depth + 1)


def _parse_starter(player_dict) -> bool:
    """Best-effort sul flag titolare; la chiave 'panchina' ha semantica invertita."""
    lowered = {str(k).lower(): v for k, v in player_dict.items()}
    for key in _STARTER_KEYS:
        if key in lowered and lowered[key] is not None:
            truthy = str(lowered[key]).strip().lower() in ("1", "true", "t", "si", "s", "yes")
            return not truthy if key == "panchina" else truthy
    return True


# ── Risoluzione entita' interne ─────────────────────────────────────────


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


def _import_competition_lineups(db: Session, comp: Competition, match_day: int, data) -> dict:
    """Mappa le righe giocatore su LineupSubmission/LineupPlayer per una competizione."""
    teams = {
        _normalize(t.name): t
        for t in db.query(FantaTeam).filter(FantaTeam.season_id == comp.season_id).all()
    }
    players = {p.name.strip().lower(): p for p in db.query(Player).all()}

    rows_by_team: dict[str, list] = {}
    unmatched_teams: set[str] = set()
    unmatched_players: set[str] = set()
    for player_dict, fantateam in _iter_player_dicts(data):
        if not fantateam:
            continue
        rows_by_team.setdefault(fantateam, []).append(player_dict)

    imported_players = 0
    lineups = 0
    for fantateam_name, player_dicts in rows_by_team.items():
        team = teams.get(_normalize(fantateam_name))
        if not team:
            unmatched_teams.add(fantateam_name)
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
        lineup.submitted_at = datetime.utcnow()
        lineups += 1

        # Senza chiave naturale per riga, delete+reinsert e' l'unico upsert corretto.
        db.query(LineupPlayer).filter(LineupPlayer.lineup_id == lineup.id).delete()

        bench_order = 0
        for player_dict in player_dicts:
            name = str(_get_ci(player_dict, _NAME_KEYS)).strip()
            player = players.get(name.lower())
            if not player:
                unmatched_players.add(name)
                continue
            is_starter = _parse_starter(player_dict)
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


def sync_formazioni(db: Session, season_id: int) -> dict:
    """Fetch di tutte le formazioni da leghe.fantacalcio.it e import strutturato.
    Solleva SessionFileMissing/SessionExpired (gestite dal router)."""
    client = LegheClient()
    client._check_session_file()  # fail-fast: senza sessione il login sarebbe inutile
    client.login()
    risultati = client.get_tutte_le_formazioni()

    report = {}
    for slug, risultato in risultati.items():
        if risultato is None:
            report[slug] = {"ok": False, "message": "Nessun dato (timeout)"}
            continue

        leghe_id = risultato["id_comp"]
        match_day = risultato["giornata"] or 0
        entry = {"ok": True, "match_day": match_day, "raw_saved": True}

        try:
            _save_raw(db, leghe_id, slug, match_day, risultato["dati"])
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
                db, comp, match_day, risultato["dati"]
            ))
        except Exception as e:
            # Il raw e' gia' in sessione: il parsing fallito non fa fallire il sync.
            logger.error("Errore import formazioni per '%s': %s", slug, e)
            entry.update(ok=False, message="Parsing non riuscito (struttura da analizzare)")
        report[slug] = entry

    db.commit()
    return {"ok": True, "competitions": report}
