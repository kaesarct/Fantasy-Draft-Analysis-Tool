"""League, standings and competitions router."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.season import Season
from app.models.competition import Competition, CompetitionStanding, MatchResult

router = APIRouter(tags=["league"])

seasons_router = APIRouter(prefix="/seasons")
competitions_router = APIRouter(prefix="/competitions")


@seasons_router.get("")
def list_seasons(db: Session = Depends(get_db)):
    seasons = db.query(Season).order_by(Season.year_start.desc()).all()
    return [
        {"id": s.id, "label": s.label, "year_start": s.year_start,
         "year_end": s.year_end, "is_current": s.is_current}
        for s in seasons
    ]


@seasons_router.patch("/{season_id}/set-current")
def set_current_season(season_id: int, db: Session = Depends(get_db)):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(404, "Stagione non trovata")
    db.query(Season).filter(Season.is_current == True).update({"is_current": False})
    season.is_current = True
    db.commit()
    return {"ok": True, "id": season.id, "label": season.label}


@seasons_router.get("/{season_id}/competitions")
def get_season_competitions(season_id: int, db: Session = Depends(get_db)):
    comps = db.query(Competition).filter(Competition.season_id == season_id).all()
    return [
        {"id": c.id, "name": c.name, "type": c.type, "is_active": c.is_active}
        for c in comps
    ]


@seasons_router.get("/{season_id}/standings")
def get_season_standings(
    season_id: int,
    comp_type: str | None = None,
    match_day: int | None = None,
    db: Session = Depends(get_db),
):
    q = (
        db.query(CompetitionStanding)
        .join(Competition)
        .filter(Competition.season_id == season_id)
    )
    if comp_type:
        q = q.filter(Competition.type == comp_type.upper())
    if match_day:
        q = q.filter(CompetitionStanding.match_day == match_day)
    standings = q.all()
    return [
        {
            "fanta_team_id": s.fanta_team_id,
            "competition_id": s.competition_id,
            "match_day": s.match_day,
            "pts": s.pts, "wins": s.wins, "draws": s.draws, "losses": s.losses,
            "goals_for": s.goals_for, "goals_against": s.goals_against,
            "total_score": s.total_score,
        }
        for s in standings
    ]


@competitions_router.get("/{comp_id}/standings")
def get_competition_standings(comp_id: int, match_day: int | None = None, db: Session = Depends(get_db)):
    q = db.query(CompetitionStanding).filter(CompetitionStanding.competition_id == comp_id)
    if match_day:
        q = q.filter(CompetitionStanding.match_day == match_day)
    standings = q.order_by(CompetitionStanding.match_day, CompetitionStanding.pts.desc()).all()
    return [
        {
            "fanta_team_id": s.fanta_team_id, "match_day": s.match_day,
            "pts": s.pts, "wins": s.wins, "draws": s.draws, "losses": s.losses,
            "goals_for": s.goals_for, "goals_against": s.goals_against,
            "total_score": s.total_score,
        }
        for s in standings
    ]


@competitions_router.get("/{comp_id}/matches")
def get_competition_matches(comp_id: int, match_day: int | None = None, db: Session = Depends(get_db)):
    q = db.query(MatchResult).filter(MatchResult.competition_id == comp_id)
    if match_day:
        q = q.filter(MatchResult.match_day == match_day)
    results = q.order_by(MatchResult.match_day).all()
    return [
        {
            "id": r.id, "match_day": r.match_day, "phase": r.phase,
            "home_team_id": r.fanta_team_home_id,
            "away_team_id": r.fanta_team_away_id,
            "score_home": r.score_home, "score_away": r.score_away,
            "goals_home": r.goals_home, "goals_away": r.goals_away,
            "pts_home": r.pts_home, "pts_away": r.pts_away,
        }
        for r in results
    ]


router.include_router(seasons_router)
router.include_router(competitions_router)
