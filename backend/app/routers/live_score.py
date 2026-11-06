"""Public API router for SILVER live score calculation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.leghe_client import LegheDisabledError
from app.services.live_score_service import get_silver_live_data

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/silver")
def get_silver_live(
    match_day: int | None = Query(
        None,
        ge=1,
        le=38,
        description="Giornata di Serie A (se omessa, rileva automaticamente la giornata corrente)",
    ),
    refresh: bool = Query(
        False,
        description="Forza il ricalcolo ignorando la cache di breve durata",
    ),
    db: Session = Depends(get_db),
):
    """Restituisce la classifica live e le formazioni calcolate della competizione SILVER.
    Endpoint pubblico accessibile a tutti senza autenticazione.
    """
    try:
        return get_silver_live_data(db=db, serie_a_day=match_day, force_refresh=refresh)
    except LegheDisabledError as exc:
        # Il Live usa le formazioni di lega, che esistono solo su leghe.fantacalcio.it.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Errore nel recupero dei punteggi live SILVER: {exc}",
        ) from exc

