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
from app.models.player import Player, PlayerSnapshot, PlayerMatchScore, PlayerArchiveSeasonStat
from app.models.player_merge import PlayerMergeDismissal
from app.models.season import Season
from app.models.season_data import PlayerSeasonStat as ExcelPlayerSeasonStat, PlayerSeasonPrice
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
    """True se una stringa e' l'altra con in piu' una singola parola finale
    di disambiguazione: un'iniziale ("romagnoli" / "romagnoli a") o un nome
    di battesimo intero ("accardi" / "accardi pietro")."""
    shorter, longer = (norm_a, norm_b) if len(norm_a) < len(norm_b) else (norm_b, norm_a)
    if not longer.startswith(shorter + " "):
        return False
    suffix = longer[len(shorter) + 1:]
    return 1 <= len(suffix) <= 20 and " " not in suffix


def _ordered_pair(id_a: int, id_b: int) -> tuple[int, int]:
    return (id_a, id_b) if id_a < id_b else (id_b, id_a)


def _player_seasons_maps(db: Session):
    """Stagioni (id) in cui compare ogni giocatore, per player_id (archivio
    storico e quotazioni live) e per fanta_id (import Excel 2015-16+) — utile
    per capire se due candidati al merge si sovrappongono (probabile persona
    diversa) o si susseguono (probabile stesso giocatore rinominato)."""
    seasons_by_player: dict[int, set[int]] = {}
    seasons_by_fanta: dict[int, set[int]] = {}

    for pid, sid in db.query(PlayerArchiveSeasonStat.player_id, PlayerArchiveSeasonStat.season_id).distinct().all():
        seasons_by_player.setdefault(pid, set()).add(sid)
    for pid, sid in db.query(PlayerSnapshot.player_id, PlayerSnapshot.season_id).distinct().all():
        seasons_by_player.setdefault(pid, set()).add(sid)
    for fid, sid in db.query(ExcelPlayerSeasonStat.fanta_player_id, ExcelPlayerSeasonStat.season_id).distinct().all():
        seasons_by_fanta.setdefault(fid, set()).add(sid)
    for fid, sid in db.query(PlayerSeasonPrice.fanta_player_id, PlayerSeasonPrice.season_id).distinct().all():
        seasons_by_fanta.setdefault(fid, set()).add(sid)

    labels = {s.id: s.label for s in db.query(Season.id, Season.label).all()}
    return seasons_by_player, seasons_by_fanta, labels


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
    seasons_by_player, seasons_by_fanta, season_labels = _player_seasons_maps(db)

    def _summary(p: Player) -> dict:
        entry = {
            "id": p.id, "fanta_id": p.fanta_id, "name": p.name,
            "secondary_role": p.secondary_role,
        }
        entry.update(player_range_entry(p, hist_ranges, live_ranges, roles))
        season_ids = set(seasons_by_player.get(p.id, set()))
        if p.fanta_id:
            season_ids |= seasons_by_fanta.get(p.fanta_id, set())
        entry["seasons"] = sorted(season_labels.get(sid, str(sid)) for sid in season_ids)
        return entry

    return [
        {"player_a": _summary(a), "player_b": _summary(b)}
        for a, b in pairs
    ]


@router.get("/role-conflicts")
def get_role_conflicts(db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    """Giocatori con nome ESATTAMENTE identico (non solo simile, quindi mai
    passati dal check /candidates) che pero' hanno ruoli incompatibili tra
    le stagioni — segno quasi certo che il match per nome ha unito due
    persone reali diverse (es. un portiere storico e un difensore moderno
    con lo stesso cognome nudo, senza alcuna iniziale a disambiguare)."""
    labels = {s.id: s.label for s in db.query(Season.id, Season.label).all()}

    entries_by_player: dict[int, list[dict]] = {}

    def _add(pid, source, row_id, season_id, role, team):
        if not role:
            return
        entries_by_player.setdefault(pid, []).append({
            "source": source, "row_id": row_id, "season_id": season_id,
            "season_label": labels.get(season_id), "role": role, "team": team,
        })

    for r in db.query(PlayerArchiveSeasonStat).all():
        _add(r.player_id, "archive", r.id, r.season_id, r.role, r.team_name)

    fanta_id_by_player = dict(
        db.query(Player.id, Player.fanta_id).filter(Player.fanta_id.isnot(None)).all()
    )
    player_id_by_fanta = {v: k for k, v in fanta_id_by_player.items()}

    for r in db.query(ExcelPlayerSeasonStat).all():
        pid = player_id_by_fanta.get(r.fanta_player_id)
        if pid:
            _add(pid, "excel_stat", r.id, r.season_id, r.role, r.team)
    for r in db.query(PlayerSeasonPrice).all():
        pid = player_id_by_fanta.get(r.fanta_player_id)
        if pid:
            _add(pid, "excel_price", r.id, r.season_id, r.role, r.team)

    players_by_id = {
        p.id: p for p in db.query(Player).filter(Player.id.in_(entries_by_player.keys())).all()
    }

    conflicts = []
    for pid, entries in entries_by_player.items():
        roles = {e["role"] for e in entries}
        if len(roles) < 2:
            continue
        p = players_by_id.get(pid)
        entries.sort(key=lambda e: (e["season_id"], e["source"]))
        anchor_roles = {e["role"] for e in entries if e["source"] != "archive"}
        # "P" (portiere) misto a un ruolo di movimento e' impossibile per una
        # persona reale: segnale forte di due giocatori diversi uniti per
        # coincidenza di cognome. Un mix D/C/A e' spesso solo evoluzione di
        # ruolo nella carriera dello stesso giocatore (es. terzino/mediano).
        severity = "alta" if "P" in roles and len(roles) > 1 else "bassa"
        conflicts.append({
            "player_id": pid,
            "player_name": p.name if p else None,
            "fanta_id": fanta_id_by_player.get(pid),
            "anchor_roles": sorted(anchor_roles),
            "severity": severity,
            "entries": entries,
        })
    conflicts.sort(key=lambda c: (c["severity"] != "alta", c["player_name"] or ""))
    return conflicts


class SplitRoleRequest(BaseModel):
    player_id: int
    role: str
    new_name: str | None = None


@router.post("/split-role")
def split_role(payload: SplitRoleRequest, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    """Estrae in un nuovo giocatore le sole righe d'archivio storico
    (player_id) con il ruolo indicato. Non tocca mai fanta_id/dati
    Excel/live: se quel ruolo e' anche quello dell'identita' con fanta_id,
    va separato l'ALTRO ruolo (l'identita' con fanta_id resta dove e')."""
    original = db.query(Player).filter(Player.id == payload.player_id).first()
    if not original:
        raise HTTPException(404, "Giocatore non trovato")

    archive_rows = db.query(PlayerArchiveSeasonStat).filter(
        PlayerArchiveSeasonStat.player_id == payload.player_id,
        PlayerArchiveSeasonStat.role == payload.role,
    ).all()
    if not archive_rows:
        raise HTTPException(400, "Nessuna riga d'archivio con questo ruolo per questo giocatore")

    if original.fanta_id:
        excel_roles = {
            r[0] for r in db.query(ExcelPlayerSeasonStat.role).filter(
                ExcelPlayerSeasonStat.fanta_player_id == original.fanta_id,
                ExcelPlayerSeasonStat.role.isnot(None),
            ).all()
        } | {
            r[0] for r in db.query(PlayerSeasonPrice.role).filter(
                PlayerSeasonPrice.fanta_player_id == original.fanta_id,
                PlayerSeasonPrice.role.isnot(None),
            ).all()
        }
        if payload.role in excel_roles:
            raise HTTPException(
                400,
                "Questo ruolo e' collegato ai dati Excel/live (fanta_id) del giocatore: "
                "non puo' essere separato. Separa l'altro ruolo.",
            )

    new_player = Player(name=payload.new_name or original.name, role=payload.role)
    db.add(new_player)
    db.flush()
    for r in archive_rows:
        r.player_id = new_player.id
    db.flush()

    if original.role == payload.role:
        remaining_archive = db.query(PlayerArchiveSeasonStat).filter(
            PlayerArchiveSeasonStat.player_id == original.id
        ).first()
        if remaining_archive:
            original.role = remaining_archive.role
        elif original.fanta_id:
            remaining_excel = (
                db.query(ExcelPlayerSeasonStat.role)
                .filter(ExcelPlayerSeasonStat.fanta_player_id == original.fanta_id, ExcelPlayerSeasonStat.role.isnot(None))
                .first()
                or db.query(PlayerSeasonPrice.role)
                .filter(PlayerSeasonPrice.fanta_player_id == original.fanta_id, PlayerSeasonPrice.role.isnot(None))
                .first()
            )
            if remaining_excel:
                original.role = remaining_excel[0]

    db.commit()
    return {"ok": True, "new_player_id": new_player.id, "moved_rows": len(archive_rows)}


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
    (PlayerArchiveSeasonStat, "player_id", ["season_id", "team_name"]),
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

    # Il giocatore "remove" sta per essere cancellato: ripulisco ogni suo
    # rifiuto, non solo quello con "keep" (potrebbe essere stato rifiutato
    # anche contro un terzo giocatore prima di una separazione di ruoli,
    # rendendo quel rifiuto obsoleto) — altrimenti la FK blocca la delete.
    db.query(PlayerMergeDismissal).filter(
        (PlayerMergeDismissal.player_id_low == payload.remove_id)
        | (PlayerMergeDismissal.player_id_high == payload.remove_id)
    ).delete()

    db.delete(remove)
    db.commit()
    return {"merged": True, "relinked": relinked}
