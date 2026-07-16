"""Injuries router."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import date
from app.database import get_db
from app.models.injury import InjuryPlayer
from app.models.player import PlayerMatchScore
from app.services.auth_service import require_admin
from app.services.fanta_client import fanta_client
from app.services.sync_service import sync_votes

router = APIRouter(prefix="/injuries", tags=["injuries"])


class InjuryCreate(BaseModel):
    player_id: int
    season_id: int
    report_date: date | None = None
    expected_weeks: int | None = None
    expected_return: date | None = None
    notes: str | None = None


@router.get("")
def list_injuries(season_id: int | None = None, active_only: bool = True, db: Session = Depends(get_db)):
    q = db.query(InjuryPlayer)
    if season_id:
        q = q.filter(InjuryPlayer.season_id == season_id)
    if active_only:
        q = q.filter(InjuryPlayer.is_active == True)
    injuries = q.all()
    return [
        {
            "id": i.id, "player_id": i.player_id,
            "player_name": i.player.name if i.player else None,
            "report_date": i.report_date, "expected_weeks": i.expected_weeks,
            "expected_return": i.expected_return, "confirmed_return": i.confirmed_return,
            "qualifies_for_temp_sub": i.qualifies_for_temp_sub, "is_active": i.is_active,
            "notes": i.notes, "created_at": i.created_at,
        }
        for i in injuries
    ]


@router.post("")
def create_injury(payload: InjuryCreate, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    existing = db.query(InjuryPlayer).filter(
        InjuryPlayer.player_id == payload.player_id,
        InjuryPlayer.season_id == payload.season_id,
        InjuryPlayer.is_active == True,
    ).first()
    if existing:
        raise HTTPException(409, "Giocatore già in lista infortunati")

    qualifies = (payload.expected_weeks or 0) >= 8
    injury = InjuryPlayer(
        player_id=payload.player_id,
        season_id=payload.season_id,
        report_date=payload.report_date,
        expected_weeks=payload.expected_weeks,
        expected_return=payload.expected_return,
        notes=payload.notes,
        qualifies_for_temp_sub=qualifies,
    )
    db.add(injury)
    db.commit()
    db.refresh(injury)
    return {"id": injury.id, "qualifies_for_temp_sub": injury.qualifies_for_temp_sub}


@router.patch("/{injury_id}/recover")
def mark_recovered(
    injury_id: int,
    confirmed_return: date,
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    injury = db.query(InjuryPlayer).filter(InjuryPlayer.id == injury_id).first()
    if not injury:
        raise HTTPException(404)
    injury.confirmed_return = confirmed_return
    injury.is_active = False
    db.commit()
    return {"ok": True}


@router.post("/check-recovery")
def check_recovery(
    season_id: int,
    match_day: int | None = Query(None),
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    day = match_day if match_day is not None else fanta_client.get_last_matchday()
    if day < 0:
        raise HTTPException(502, "Impossibile determinare l'ultima giornata da fantacalcio.it")

    sync_result = sync_votes(db, season_id, day)
    if not sync_result.get("ok"):
        raise HTTPException(502, sync_result.get("message", "Errore durante il download dei voti"))

    active = db.query(InjuryPlayer).filter(
        InjuryPlayer.season_id == season_id,
        InjuryPlayer.is_active == True,
    ).all()

    returned, still_injured = [], []
    for inj in active:
        score = db.query(PlayerMatchScore).filter(
            PlayerMatchScore.player_id == inj.player_id,
            PlayerMatchScore.season_id == season_id,
            PlayerMatchScore.match_day == day,
            PlayerMatchScore.vote.isnot(None),
        ).first()
        entry = {
            "id": inj.id, "player_id": inj.player_id,
            "player_name": inj.player.name if inj.player else None,
        }
        if score:
            inj.is_active = False
            inj.confirmed_return = date.today()
            returned.append(entry)
        else:
            still_injured.append(entry)

    db.commit()
    return {"match_day": day, "returned": returned, "still_injured": still_injured}


@router.delete("/{injury_id}")
def delete_injury(injury_id: int, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    injury = db.query(InjuryPlayer).filter(InjuryPlayer.id == injury_id).first()
    if not injury:
        raise HTTPException(404)
    db.delete(injury)
    db.commit()
    return {"ok": True}
