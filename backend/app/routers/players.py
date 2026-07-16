"""Players router."""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.player import Player, PlayerSnapshot, PlayerMatchScore

router = APIRouter(prefix="/players", tags=["players"])


@router.get("")
def list_players(
    search: str | None = Query(None),
    role: str | None = Query(None),
    team_id: int | None = Query(None),
    season_id: int | None = Query(None, description="Limita ai giocatori presenti nelle quotazioni di questa stagione"),
    db: Session = Depends(get_db),
):
    q = db.query(Player)
    if search:
        q = q.filter(Player.name.ilike(f"%{search}%"))
    if role:
        q = q.filter(Player.role == role.upper())
    if team_id:
        q = q.filter(Player.serie_a_team_id == team_id)
    if season_id:
        quoted_player_ids = db.query(PlayerSnapshot.player_id).filter(
            PlayerSnapshot.season_id == season_id
        ).distinct().subquery()
        q = q.filter(Player.id.in_(quoted_player_ids))
    players = q.order_by(Player.name).all()
    return [
        {
            "id": p.id,
            "fanta_id": p.fanta_id,
            "name": p.name,
            "role": p.role,
            "secondary_role": p.secondary_role,
            "serie_a_team_id": p.serie_a_team_id,
        }
        for p in players
    ]


@router.get("/{player_id}")
def get_player(player_id: int, db: Session = Depends(get_db)):
    p = db.query(Player).filter(Player.id == player_id).first()
    if not p:
        raise HTTPException(404, "Player not found")
    return {
        "id": p.id, "fanta_id": p.fanta_id, "name": p.name,
        "role": p.role, "secondary_role": p.secondary_role,
        "serie_a_team_id": p.serie_a_team_id,
        "serie_a_team_name": p.serie_a_team.name if p.serie_a_team else None,
    }


@router.get("/{player_id}/history")
def get_player_history(player_id: int, season_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(PlayerSnapshot).filter(PlayerSnapshot.player_id == player_id)
    if season_id:
        q = q.filter(PlayerSnapshot.season_id == season_id)
    snaps = q.order_by(PlayerSnapshot.season_id, PlayerSnapshot.match_day).all()
    return [
        {
            "match_day": s.match_day, "season_id": s.season_id,
            "price": s.price, "price_diff": s.price_diff,
            "fvm": s.fvm, "fvm_mantra": s.fvm_mantra,
        }
        for s in snaps
    ]


@router.get("/{player_id}/scores")
def get_player_scores(player_id: int, season_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(PlayerMatchScore).filter(PlayerMatchScore.player_id == player_id)
    if season_id:
        q = q.filter(PlayerMatchScore.season_id == season_id)
    scores = q.order_by(PlayerMatchScore.season_id, PlayerMatchScore.match_day).all()
    return [
        {
            "match_day": s.match_day, "season_id": s.season_id,
            "vote": s.vote, "goals": s.goals, "assists": s.assists,
            "yellow_cards": s.yellow_cards, "red_cards": s.red_cards,
            "bonus_total": s.bonus_total, "malus_total": s.malus_total,
            "total_score": s.total_score,
        }
        for s in scores
    ]
