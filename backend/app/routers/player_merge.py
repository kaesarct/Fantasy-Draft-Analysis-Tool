"""Tool di merge manuale per giocatori duplicati con nome simile ma non
identico (es. "Martinez L" / "Martinez L.", "Romagnoli" / "Romagnoli A").

Le migrazioni automatiche in database.py sistemano solo i nomi identici:
qui l'unione è sempre una scelta esplicita dell'admin (mai automatica), per
non rischiare di fondere due giocatori realmente distinti con lo stesso
cognome."""
import re
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.player import Player, PlayerSnapshot, PlayerMatchScore
from app.models.player_merge import PlayerMergeDismissal
from app.models.fanta_team import FantaRoster, FantaRosterTempSub
from app.models.injury import InjuryPlayer
from app.models.serie_a_injury import SerieAInjuryReport, SerieAInjuryArchive
from app.models.trade import TradeItem
from app.models.lineup import LineupPlayer
from app.models.auction import AuctionBid
from app.services.auth_service import require_admin
from app.routers.players import aggregate_player_ranges, player_range_entry

router = APIRouter(prefix="/player-merge", tags=["player-merge"])


def _normalize_name(name: str) -> str:
    n = name.strip().lower()
    n = re.sub(r"\s+", " ", n)
    if n.endswith("."):
        n = n[:-1]
    return n


def _suffix_variant(norm_a: str, norm_b: str) -> bool:
    """True se una stringa e' l'altra con in piu' un suffisso breve
    (1-3 lettere, es. "romagnoli" / "romagnoli a")."""
    shorter, longer = (norm_a, norm_b) if len(norm_a) < len(norm_b) else (norm_b, norm_a)
    if not longer.startswith(shorter + " "):
        return False
    suffix = longer[len(shorter) + 1:]
    return 1 <= len(suffix) <= 3


def _ordered_pair(id_a: int, id_b: int) -> tuple[int, int]:
    return (id_a, id_b) if id_a < id_b else (id_b, id_a)


@router.get("/candidates")
def get_merge_candidates(db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    players = db.query(Player).order_by(Player.name).all()
    dismissed = {
        (d.player_id_low, d.player_id_high)
        for d in db.query(PlayerMergeDismissal).all()
    }

    # Bucket per prima parola normalizzata, per non confrontare tutti-contro-
    # tutti (~1000 giocatori): due nomi simili condividono sempre la prima parola.
    buckets: dict[str, list] = {}
    for p in players:
        norm = _normalize_name(p.name)
        first_word = norm.split(" ", 1)[0]
        buckets.setdefault(first_word, []).append((p, norm))

    pairs = []
    seen_ids = set()
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                p_a, norm_a = bucket[i]
                p_b, norm_b = bucket[j]
                if norm_a == norm_b or _suffix_variant(norm_a, norm_b):
                    key = _ordered_pair(p_a.id, p_b.id)
                    if key in dismissed or key in seen_ids:
                        continue
                    seen_ids.add(key)
                    pairs.append((p_a, p_b))

    hist_ranges, live_ranges, roles = aggregate_player_ranges(db)

    def _summary(p: Player) -> dict:
        entry = {
            "id": p.id, "fanta_id": p.fanta_id, "name": p.name,
            "secondary_role": p.secondary_role,
        }
        entry.update(player_range_entry(p, hist_ranges, live_ranges, roles))
        return entry

    return [
        {"player_a": _summary(a), "player_b": _summary(b)}
        for a, b in pairs
    ]


class DismissRequest(BaseModel):
    player_id_a: int
    player_id_b: int


@router.post("/dismiss")
def dismiss_candidate(payload: DismissRequest, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    low, high = _ordered_pair(payload.player_id_a, payload.player_id_b)
    existing = db.query(PlayerMergeDismissal).filter(
        PlayerMergeDismissal.player_id_low == low,
        PlayerMergeDismissal.player_id_high == high,
    ).first()
    if not existing:
        db.add(PlayerMergeDismissal(player_id_low=low, player_id_high=high, dismissed_at=datetime.utcnow()))
        db.commit()
    return {"ok": True}


# Tabelle collegate a players.id senza vincolo unico sul player_id: repoint diretto.
_SIMPLE_TABLES = [
    (FantaRosterTempSub, "replacement_player_id"),
    (InjuryPlayer, "player_id"),
    (SerieAInjuryReport, "player_id"),
    (SerieAInjuryArchive, "player_id"),
    (TradeItem, "player_id"),
    (LineupPlayer, "player_id"),
]

# Tabelle con vincolo unico che include player_id: repoint riga per riga,
# saltando i conflitti (stessa logica gia' validata in
# database.py::_migrate_dedupe_players).
_UNIQUE_TABLES = [
    (FantaRoster, "player_id", ["fanta_team_id", "season_id"]),
    (AuctionBid, "player_id", ["auction_id"]),
    (PlayerSnapshot, "player_id", ["season_id", "match_day"]),
    (PlayerMatchScore, "player_id", ["season_id", "match_day"]),
]


def _row_diff(model, keep_row, remove_row, fk_field: str) -> dict[str, dict[str, Any]]:
    """Colonne che differiscono tra le due righe in conflitto (escluse id e fk_field).
    Generico: riusabile per tutti i modelli di _UNIQUE_TABLES."""
    excluded = {"id", fk_field}
    diff: dict[str, dict[str, Any]] = {}
    for col in model.__table__.columns:
        if col.name in excluded:
            continue
        kv, rv = getattr(keep_row, col.name), getattr(remove_row, col.name)
        if kv != rv:
            diff[col.name] = {"keep": kv, "remove": rv}
    return diff


def _resolution_key(table: str, key_values: dict[str, int]) -> tuple:
    return (table, tuple(sorted(key_values.items())))


class ConflictResolution(BaseModel):
    table: str
    key_values: dict[str, int]
    winner: Literal["keep", "remove"]


class MergeRequest(BaseModel):
    keep_id: int
    remove_id: int
    resolutions: list[ConflictResolution] = []


@router.post("/merge")
def merge_players(payload: MergeRequest, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    if payload.keep_id == payload.remove_id:
        raise HTTPException(400, "keep_id e remove_id devono essere diversi")

    keep = db.query(Player).filter(Player.id == payload.keep_id).first()
    remove = db.query(Player).filter(Player.id == payload.remove_id).first()
    if not keep or not remove:
        raise HTTPException(404, "Giocatore non trovato")

    known_tables = {model.__tablename__ for model, _, _ in _UNIQUE_TABLES}
    unknown = [r.table for r in payload.resolutions if r.table not in known_tables]
    if unknown:
        raise HTTPException(400, f"Tabella di risoluzione non valida: {unknown[0]}")

    resolutions_by_key = {
        _resolution_key(r.table, r.key_values): r.winner for r in payload.resolutions
    }

    relinked: dict[str, int] = {}
    conflicts: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for model, fk_field in _SIMPLE_TABLES:
        count = (
            db.query(model)
            .filter(getattr(model, fk_field) == payload.remove_id)
            .update({fk_field: payload.keep_id})
        )
        if count:
            relinked[model.__tablename__] = count

    for model, fk_field, key_fields in _UNIQUE_TABLES:
        table_name = model.__tablename__
        rows = db.query(model).filter(getattr(model, fk_field) == payload.remove_id).all()
        moved = 0
        for row in rows:
            key_values = {f: getattr(row, f) for f in key_fields}
            conflict_row = (
                db.query(model)
                .filter(
                    getattr(model, fk_field) == payload.keep_id,
                    *[getattr(model, f) == key_values[f] for f in key_fields],
                )
                .first()
            )
            if not conflict_row:
                setattr(row, fk_field, payload.keep_id)
                moved += 1
                continue

            winner = resolutions_by_key.get(_resolution_key(table_name, key_values))
            if winner is None:
                conflicts.append({
                    "table": table_name, "key_values": key_values,
                    "diff": _row_diff(model, conflict_row, row, fk_field),
                })
                continue

            loser_row = row if winner == "keep" else conflict_row
            try:
                with db.begin_nested():
                    db.delete(loser_row)
                    db.flush()
            except IntegrityError:
                unresolved.append({
                    "table": table_name, "key_values": key_values,
                    "reason": "riga ancora referenziata da un'altra tabella; va risolta a mano",
                })
                conflicts.append({
                    "table": table_name, "key_values": key_values,
                    "diff": _row_diff(model, conflict_row, row, fk_field),
                })
                continue

            if winner == "remove":
                setattr(row, fk_field, payload.keep_id)
                moved += 1
            # winner == "keep": la riga perdente (row) e' stata gia' cancellata sopra

        if moved:
            relinked[table_name] = relinked.get(table_name, 0) + moved

    db.flush()

    still_referenced = any(
        db.query(model).filter(getattr(model, fk_field) == payload.remove_id).first()
        for model, fk_field in _SIMPLE_TABLES
    ) or any(
        db.query(model).filter(getattr(model, fk_field) == payload.remove_id).first()
        for model, fk_field, _ in _UNIQUE_TABLES
    )

    if still_referenced:
        db.commit()
        return {"merged": False, "relinked": relinked, "conflicts": conflicts, "unresolved": unresolved}

    low, high = _ordered_pair(payload.keep_id, payload.remove_id)
    db.query(PlayerMergeDismissal).filter(
        PlayerMergeDismissal.player_id_low == low,
        PlayerMergeDismissal.player_id_high == high,
    ).delete()

    db.delete(remove)
    db.commit()
    return {"merged": True, "relinked": relinked}
