"""History router — import e consultazione dati storici di stagione."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import require_admin
from app.services.season_import import DATA_TYPE_CONFIG, build_csv, import_season_data

router = APIRouter(prefix="/history", tags=["history"])


def _validate_data_type(data_type: str) -> str:
    if data_type not in DATA_TYPE_CONFIG:
        raise HTTPException(status_code=400, detail="data_type deve essere 'stats' o 'prices'")
    return data_type


@router.post("/seasons/{season_id}/import")
def import_season(
    season_id: int,
    data_type: str = Query(..., description="'stats' o 'prices'"),
    force: bool = Query(False),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    result = import_season_data(db, season_id, _validate_data_type(data_type), force)
    if not result["ok"]:
        raise HTTPException(status_code=502, detail=result["message"])
    return result


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
