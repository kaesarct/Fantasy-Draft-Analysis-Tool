"""Players router."""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.player import Player, PlayerSnapshot, PlayerMatchScore
from app.models.season import Season
from app.models.season_data import PlayerSeasonStat, PlayerSeasonPrice, PlayerSeasonVote

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
    p = db.query(Player).filter(Player.id == player_id).first()
    if not p:
        raise HTTPException(404, "Player not found")

    q = db.query(PlayerMatchScore).filter(PlayerMatchScore.player_id == player_id)
    if season_id:
        q = q.filter(PlayerMatchScore.season_id == season_id)
    scores = q.order_by(PlayerMatchScore.season_id, PlayerMatchScore.match_day).all()

    if season_id and p.fanta_id:
        historical = (
            db.query(PlayerSeasonVote)
            .filter(
                PlayerSeasonVote.season_id == season_id,
                PlayerSeasonVote.fanta_player_id == p.fanta_id,
            )
            .order_by(PlayerSeasonVote.match_day)
            .all()
        )
        if len(historical) > len(scores):
            return [
                {
                    "match_day": h.match_day, "season_id": season_id,
                    "vote": h.vote, "goals": h.goals_scored, "assists": h.assists,
                    "yellow_cards": h.yellow_cards, "red_cards": h.red_cards,
                    "bonus_total": None, "malus_total": None, "total_score": None,
                }
                for h in historical
            ]

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


@router.get("/{player_id}/season-history")
def get_player_season_history(player_id: int, db: Session = Depends(get_db)):
    p = db.query(Player).filter(Player.id == player_id).first()
    if not p:
        raise HTTPException(404, "Player not found")
    if not p.fanta_id:
        return []

    stats = {
        s.season_id: s
        for s in db.query(PlayerSeasonStat).filter(PlayerSeasonStat.fanta_player_id == p.fanta_id).all()
    }
    prices = {
        pr.season_id: pr
        for pr in db.query(PlayerSeasonPrice).filter(PlayerSeasonPrice.fanta_player_id == p.fanta_id).all()
    }
    season_ids = set(stats) | set(prices)
    if not season_ids:
        return []

    labels = {
        s.id: s.label
        for s in db.query(Season).filter(Season.id.in_(season_ids)).all()
    }

    result = []
    for sid in season_ids:
        st = stats.get(sid)
        pr = prices.get(sid)
        result.append({
            "season_id": sid,
            "season_label": labels.get(sid),
            "matches_played": st.matches_played if st else None,
            "average_vote": st.average_vote if st else None,
            "fantasy_average": st.fantasy_average if st else None,
            "goals_scored": st.goals_scored if st else None,
            "assists": st.assists if st else None,
            "yellow_cards": st.yellow_cards if st else None,
            "red_cards": st.red_cards if st else None,
            "market_value_i": pr.market_value_i if pr else None,
            "market_value_a": pr.market_value_a if pr else None,
            "difference": pr.difference if pr else None,
            "fvm": pr.fvm if pr else None,
        })
    result.sort(key=lambda r: r["season_id"], reverse=True)
    return result
