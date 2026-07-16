"""Unione manuale di due fantasquadre duplicate (es. le stesse squadre
create due volte da pipeline di import diverse, con un nome leggermente
diverso — vedi la migrazione una tantum in database.py per il caso 2023-24
gia' risolto). A differenza dei giocatori non c'e' rilevamento automatico
delle coppie: i doppioni di squadra sono rari e vanno individuati a mano
dall'admin nella pagina di gestione squadre, poi uniti qui."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.fanta_team import FantaTeam, FantaRoster, FantaTeamCoach, FantaTeamLogo
from app.models.competition import MatchResult, CompetitionStanding, CompetitionGroupTeam
from app.models.auction import AuctionBid
from app.models.trade import Trade, TradeItem
from app.models.lineup import LineupSubmission
from app.services.auth_service import require_admin

router = APIRouter(prefix="/team-merge", tags=["team-merge"])

# Tabelle collegate a fanta_teams.id senza vincolo unico sul FK: repoint diretto.
_SIMPLE_TABLES = [
    (MatchResult, "fanta_team_home_id"),
    (MatchResult, "fanta_team_away_id"),
    (AuctionBid, "fanta_team_id"),
    (Trade, "team_a_id"),
    (Trade, "team_b_id"),
    (TradeItem, "from_team_id"),
    (TradeItem, "to_team_id"),
]

# Tabelle con vincolo unico che include il FK: repoint riga per riga,
# saltando i conflitti (stessa logica di player_merge.py).
_UNIQUE_TABLES = [
    (FantaRoster, "fanta_team_id", ["player_id", "season_id"]),
    (FantaTeamCoach, "fanta_team_id", ["allenatore_id"]),
    (FantaTeamLogo, "fanta_team_id", ["season_id"]),
    (CompetitionStanding, "fanta_team_id", ["competition_id", "match_day"]),
    (CompetitionGroupTeam, "fanta_team_id", ["group_id"]),
    (LineupSubmission, "fanta_team_id", ["competition_id", "match_day"]),
]


class MergeRequest(BaseModel):
    keep_id: int
    remove_id: int


@router.post("/merge")
def merge_teams(payload: MergeRequest, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    if payload.keep_id == payload.remove_id:
        raise HTTPException(400, "keep_id e remove_id devono essere diversi")

    keep = db.query(FantaTeam).filter(FantaTeam.id == payload.keep_id).first()
    remove = db.query(FantaTeam).filter(FantaTeam.id == payload.remove_id).first()
    if not keep or not remove:
        raise HTTPException(404, "Squadra non trovata")

    relinked: dict[str, int] = {}
    conflicts: dict[str, int] = {}

    for model, fk_field in _SIMPLE_TABLES:
        count = (
            db.query(model)
            .filter(getattr(model, fk_field) == payload.remove_id)
            .update({fk_field: payload.keep_id})
        )
        if count:
            relinked[f"{model.__tablename__}.{fk_field}"] = count

    for model, fk_field, key_fields in _UNIQUE_TABLES:
        rows = db.query(model).filter(getattr(model, fk_field) == payload.remove_id).all()
        moved = skipped = 0
        for row in rows:
            conflict = (
                db.query(model)
                .filter(
                    getattr(model, fk_field) == payload.keep_id,
                    *[getattr(model, f) == getattr(row, f) for f in key_fields],
                )
                .first()
            )
            if conflict:
                skipped += 1
                continue
            setattr(row, fk_field, payload.keep_id)
            moved += 1
        if moved:
            relinked[model.__tablename__] = moved
        if skipped:
            conflicts[model.__tablename__] = skipped

    db.flush()

    still_referenced = any(
        db.query(model).filter(getattr(model, fk_field) == payload.remove_id).first()
        for model, fk_field in _SIMPLE_TABLES
    ) or any(
        db.query(model).filter(getattr(model, fk_field) == payload.remove_id).first()
        for model, fk_field, _ in _UNIQUE_TABLES
    )

    if still_referenced:
        db.commit()
        return {"merged": False, "relinked": relinked, "conflicts": conflicts}

    db.delete(remove)
    db.commit()
    return {"merged": True, "relinked": relinked}
