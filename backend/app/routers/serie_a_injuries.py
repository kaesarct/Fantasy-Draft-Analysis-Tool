"""Router per il tracking storico infortunati Serie A (fantacalcio.it)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.serie_a_injury import SerieAInjuryReport, SerieAInjuryArchive
from app.services.auth_service import require_admin
from app.services.sync_service import sync_serie_a_injuries

router = APIRouter(prefix="/serie-a-injuries", tags=["serie-a-injuries"])


def _descriptions_payload(descriptions):
    return [
        {"description": d.description, "recorded_at": d.recorded_at}
        for d in sorted(descriptions, key=lambda d: d.recorded_at)
    ]


@router.post("/sync")
def trigger_sync(db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    return sync_serie_a_injuries(db)


@router.get("")
def list_active(db: Session = Depends(get_db)):
    reports = (
        db.query(SerieAInjuryReport)
        .order_by(SerieAInjuryReport.team_name, SerieAInjuryReport.player_name)
        .all()
    )
    return [
        {
            "id": r.id,
            "player_name": r.player_name,
            "team_name": r.team_name,
            "player_id": r.player_id,
            "description": r.description,
            "first_seen_at": r.first_seen_at,
            "last_seen_at": r.last_seen_at,
            "last_updated_at": r.last_updated_at,
            "descriptions": _descriptions_payload(r.descriptions),
        }
        for r in reports
    ]


@router.get("/archive")
def list_archive(db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    archives = (
        db.query(SerieAInjuryArchive)
        .order_by(SerieAInjuryArchive.ended_at.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "player_name": a.player_name,
            "team_name": a.team_name,
            "player_id": a.player_id,
            "last_description": a.last_description,
            "started_at": a.started_at,
            "ended_at": a.ended_at,
            "descriptions": _descriptions_payload(a.descriptions),
        }
        for a in archives
    ]
