"""Matches router — Serie A next matches (scraping)."""
from fastapi import APIRouter
from app.services.seriea_scraper import get_next_matches, get_probable_lineups

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("")
def next_matches():
    return get_next_matches()


@router.get("/probable-lineups")
def probable_lineups():
    return get_probable_lineups()
