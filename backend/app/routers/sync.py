"""Sync router — trigger manual data sync from fantacalcio.it."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.auth_service import require_admin
from app.services.sync_service import sync_prices, sync_votes
from app.services.formazioni_sync import sync_formazioni
from app.services.fanta_client import fanta_client

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/prices")
def trigger_sync_prices(
    season_id: int = Query(..., description="ID stagione corrente"),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    return sync_prices(db, season_id)


@router.post("/votes")
def trigger_sync_votes(
    season_id: int = Query(...),
    match_day: int | None = Query(None),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    return sync_votes(db, season_id, match_day)


@router.post("/resync-season")
def trigger_resync_season(
    season_id: int = Query(..., description="ID stagione da risincronizzare"),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    """Rilancia quotazioni + voti di ogni giornata gia' giocata (utile dopo
    aver corretto un bug di sync: sistema in un colpo solo tutte le
    giornate della stagione corrente, non solo l'ultima)."""
    last_day = fanta_client.get_last_matchday()
    if last_day <= 0:
        raise HTTPException(400, "Impossibile rilevare la giornata corrente da fantacalcio.it")
    prices_result = sync_prices(db, season_id)
    votes_results = [
        {"match_day": day, **sync_votes(db, season_id, day)}
        for day in range(1, last_day + 1)
    ]
    return {"ok": True, "match_day": last_day, "prices": prices_result, "votes": votes_results}


@router.post("/formazioni")
def trigger_sync_formazioni(
    season_id: int = Query(..., description="ID stagione interna"),
    match_day: int | None = Query(None),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    try:
        return sync_formazioni(db, season_id, match_day)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"Login leghe fallito: {e}")
