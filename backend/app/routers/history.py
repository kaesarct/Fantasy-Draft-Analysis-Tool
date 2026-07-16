"""History router — import e consultazione dati storici di stagione."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.season_data import PlayerSeasonVote
from app.services.auth_service import require_admin
from app.services.season_import import (
    DATA_TYPE_CONFIG, VOTES_COLUMNS, build_csv, build_votes_csv, import_season_data, import_season_votes,
)

router = APIRouter(prefix="/history", tags=["history"])


def _validate_data_type(data_type: str) -> str:
    if data_type not in DATA_TYPE_CONFIG:
        raise HTTPException(status_code=400, detail="data_type deve essere 'stats' o 'prices'")
    return data_type


@router.post("/seasons/{season_id}/import")
def import_season(
    season_id: int,
    data_type: str = Query(..., description="'stats', 'prices' o 'votes'"),
    force: bool = Query(False),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    if data_type == "votes":
        result = import_season_votes(db, season_id, force)
    else:
        result = import_season_data(db, season_id, _validate_data_type(data_type), force)
    if not result["ok"]:
        raise HTTPException(status_code=502, detail=result["message"])
    return result


@router.get("/seasons/{season_id}/votes/matchdays")
def get_season_votes_matchdays(season_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(PlayerSeasonVote.match_day)
        .filter(PlayerSeasonVote.season_id == season_id)
        .distinct()
        .order_by(PlayerSeasonVote.match_day)
        .all()
    )
    return [r[0] for r in rows]


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
    return _query_season_rows(db, season_id, "stats", search)


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
    buffer = build_csv(db, season_id, _validate_data_type(data_type))
    filename = f"{data_type}_season_{season_id}.csv"
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
