"""History router — import e consultazione dati storici di stagione."""
import csv
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.player import Player, PlayerArchiveSeasonStat
from app.models.season_data import PlayerSeasonStat, PlayerSeasonVote
from app.services.auth_service import require_admin
from app.services.season_import import (
    DATA_TYPE_CONFIG, VOTES_COLUMNS, build_csv, build_votes_csv, import_season_data, import_season_votes,
)

router = APIRouter(prefix="/history", tags=["history"])

# Colonne del tab "Statistiche" (STATS_COLUMNS in history.component.ts) — riusate
# tali e quali per le stagioni 2006-07..2014-15, dove il dato viene dall'archivio
# pianetafanta (PlayerArchiveSeasonStat) invece che dall'export fantacalcio.it.
_ARCHIVE_STATS_FIELDS = [
    "fanta_player_id", "player_name", "role", "team", "matches_played",
    "average_vote", "fantasy_average", "goals_scored", "assists",
    "yellow_cards", "red_cards",
]


def _query_archive_stats(db: Session, season_id: int, search: str | None = None) -> list[dict]:
    """Fallback per le stagioni pre-2015: l'export fantacalcio.it (PlayerSeasonStat)
    non le copre, ma l'archivio pianetafanta (PlayerArchiveSeasonStat) sì — solo
    voti/statistiche, mai quotazioni (quella tabella non ha colonne prezzo)."""
    q = (
        db.query(PlayerArchiveSeasonStat, Player.name)
        .join(Player, Player.id == PlayerArchiveSeasonStat.player_id)
        .filter(PlayerArchiveSeasonStat.season_id == season_id)
    )
    if search:
        q = q.filter(Player.name.ilike(f"%{search}%"))
    return [
        {
            "fanta_player_id": stat.player_id,
            "player_name": name,
            "role": stat.role,
            "team": stat.team_name,
            "matches_played": stat.presences,
            "average_vote": stat.vote_fantacalcio,
            "fantasy_average": None,
            "goals_scored": stat.goals_scored,
            "assists": stat.assists,
            "yellow_cards": stat.yellow_cards,
            "red_cards": stat.red_cards,
        }
        for stat, name in q.order_by(Player.name).all()
    ]


def _validate_data_type(data_type: str) -> str:
    if data_type not in DATA_TYPE_CONFIG:
        raise HTTPException(status_code=400, detail="data_type deve essere 'stats' o 'prices'")
    return data_type


@router.post("/seasons/{season_id}/import")
def import_season(
    season_id: int,
    data_type: str = Query(..., description="'stats', 'prices' o 'votes'"),
    force: bool = Query(False),
    match_day: int | None = Query(None, ge=1, le=38, description="Solo per data_type='votes': importa una singola giornata"),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    if data_type == "votes":
        result = import_season_votes(db, season_id, force, match_day)
    else:
        result = import_season_data(db, season_id, _validate_data_type(data_type), force)
    if not result["ok"]:
        raise HTTPException(status_code=502, detail=result["message"])
    return result


@router.get("/seasons/{season_id}/votes")
def get_season_votes(
    season_id: int,
    match_day: int | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(PlayerSeasonVote).filter(PlayerSeasonVote.season_id == season_id)
    if match_day is not None:
        query = query.filter(PlayerSeasonVote.match_day == match_day)
    if search:
        query = query.filter(PlayerSeasonVote.player_name.ilike(f"%{search}%"))
    fields = ["fanta_player_id", *VOTES_COLUMNS]
    return [
        {field: getattr(record, field) for field in fields}
        for record in query.order_by(PlayerSeasonVote.match_day, PlayerSeasonVote.player_name).all()
    ]


@router.get("/seasons/{season_id}/votes/csv")
def download_season_votes_csv(
    season_id: int,
    match_day: int | None = Query(None),
    db: Session = Depends(get_db),
):
    buffer = build_votes_csv(db, season_id, match_day)
    suffix = f"_g{match_day}" if match_day is not None else ""
    filename = f"votes_season_{season_id}{suffix}.csv"
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/seasons/{season_id}/stats")
def get_season_stats(
    season_id: int,
    search: str | None = Query(None),
    db: Session = Depends(get_db),
):
    rows = _query_season_rows(db, season_id, "stats", search)
    return rows if rows else _query_archive_stats(db, season_id, search)


@router.get("/seasons/{season_id}/prices")
def get_season_prices(
    season_id: int,
    search: str | None = Query(None),
    db: Session = Depends(get_db),
):
    return _query_season_rows(db, season_id, "prices", search)


def _query_season_rows(db: Session, season_id: int, data_type: str, search: str | None):
    config = DATA_TYPE_CONFIG[data_type]
    model = config["model"]
    query = db.query(model).filter(model.season_id == season_id)
    if search:
        query = query.filter(model.player_name.ilike(f"%{search}%"))
    fields = ["fanta_player_id", *config["columns"].keys()]
    return [
        {field: getattr(record, field) for field in fields}
        for record in query.order_by(model.player_name).all()
    ]


@router.get("/seasons/{season_id}/{data_type}/csv")
def download_season_csv(
    season_id: int,
    data_type: str,
    db: Session = Depends(get_db),
):
    data_type = _validate_data_type(data_type)
    has_export_data = db.query(PlayerSeasonStat.id).filter(PlayerSeasonStat.season_id == season_id).first()
    if data_type == "stats" and not has_export_data:
        rows = _query_archive_stats(db, season_id)
        text_buffer = io.StringIO()
        writer = csv.DictWriter(text_buffer, fieldnames=_ARCHIVE_STATS_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        buffer = io.BytesIO(text_buffer.getvalue().encode("utf-8"))
        buffer.seek(0)
    else:
        buffer = build_csv(db, season_id, data_type)
    filename = f"{data_type}_season_{season_id}.csv"
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
