"""Funzionalita' attive nell'ambiente: il frontend le usa per spegnere i pulsanti che non possono funzionare."""
from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/features", tags=["features"])


@router.get("")
def get_features():
    """Pubblico: indica solo se l'integrazione con leghe.fantacalcio.it e' attiva (LEGHE_API_ENABLED)."""
    return {"leghe_api_enabled": settings.leghe_api_enabled}
