"""Matches router — Serie A next matches (scraping)."""
from fastapi import APIRouter
from app.services.seriea_scraper import get_next_matches, get_probable_lineups
from app.services.fanta_client import fanta_client

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("")
def next_matches():
    return get_next_matches()


@router.get("/last-matchday")
def last_matchday():
    """Giornata rilevata automaticamente da fantacalcio.it (scraping live-serie-a)."""
    return {"match_day": fanta_client.get_last_matchday()}


@router.get("/probable-lineups")
def probable_lineups():
    return get_probable_lineups()
