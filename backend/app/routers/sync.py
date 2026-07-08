"""Sync router — trigger manual data sync from fantacalcio.it."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.sync_service import sync_prices, sync_votes
from app.services.formazioni_sync import sync_formazioni
from app.services.leghe_client import SessionExpired, SessionFileMissing

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/prices")
def trigger_sync_prices(season_id: int = Query(..., description="ID stagione corrente"), db: Session = Depends(get_db)):
    return sync_prices(db, season_id)


@router.post("/votes")
def trigger_sync_votes(
    season_id: int = Query(...),
    match_day: int | None = Query(None),
    db: Session = Depends(get_db),
):
    return sync_votes(db, season_id, match_day)


@router.post("/formazioni")
def trigger_sync_formazioni(
    season_id: int = Query(..., description="ID stagione interna"),
    db: Session = Depends(get_db),
):
    try:
        return sync_formazioni(db, season_id)
    except (SessionFileMissing, SessionExpired) as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Login leghe fallito: {e}")
