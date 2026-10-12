"""Cambi per infortunio: l'admin registra quale squadra ha sostituito un
giocatore infortunato e con chi (record informativo, rose e crediti non
vengono toccati). Regole: sostituto con quotazione attuale <= a quella
dell'infortunato; massimo MAX_SWAPS_PER_TEAM cambi a stagione per squadra,
anche se l'infortunato poi rientra."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.fanta_team import FantaTeam, FantaRoster, FantaRosterTempSub
from app.models.injury import InjuryPlayer
from app.models.player import Player, PlayerSnapshot
from app.models.season import Season
from app.services.auth_service import require_admin

router = APIRouter(prefix="/injury-swaps", tags=["injury-swaps"])

MAX_SWAPS_PER_TEAM = 3
MIN_WEEKS_BEFORE_SEASON_END = 8


def _latest_snapshot(db: Session, player_id: int, season_id: int) -> PlayerSnapshot | None:
    return (
        db.query(PlayerSnapshot)
        .filter(PlayerSnapshot.player_id == player_id, PlayerSnapshot.season_id == season_id)
        .order_by(PlayerSnapshot.match_day.desc())
        .first()
    )


def _swaps_used(db: Session, team_id: int, season_id: int) -> int:
    return (
        db.query(func.count(FantaRosterTempSub.id))
        .join(FantaRoster, FantaRoster.id == FantaRosterTempSub.roster_entry_id)
        .filter(FantaRoster.fanta_team_id == team_id, FantaRoster.season_id == season_id)
        .scalar()
    )


def _season_end_warning(db: Session, season_id: int) -> str | None:
    """Avviso (non bloccante) se mancano meno di 8 settimane alla fine della
    stagione: un infortunio nuovo potrebbe non maturare le 8 settimane prima
    dell'ultima partita di Serie A."""
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season or not season.end_date:
        return None
    days_left = (season.end_date - date.today()).days
    if days_left < MIN_WEEKS_BEFORE_SEASON_END * 7:
        return (
            f"Mancano {max(days_left, 0)} giorni alla fine della stagione ({season.end_date}): "
            f"meno di {MIN_WEEKS_BEFORE_SEASON_END} settimane, il cambio potrebbe non essere piu' utile."
        )
    return None


def _swap_payload(sub: FantaRosterTempSub) -> dict:
    return {
        "id": sub.id,
        "replacement_player_id": sub.replacement_player_id,
        "replacement_player_name": sub.replacement_player.name if sub.replacement_player else None,
        "replacement_role": sub.replacement_player.role if sub.replacement_player else None,
        "created_at": sub.created_at,
    }


@router.get("")
def list_injury_swaps(season_id: int, db: Session = Depends(get_db)):
    injuries = (
        db.query(InjuryPlayer)
        .filter(InjuryPlayer.season_id == season_id)
        .order_by(InjuryPlayer.created_at.desc())
        .all()
    )
    result = []
    for inj in injuries:
        snap = _latest_snapshot(db, inj.player_id, season_id)
        rosters = (
            db.query(FantaRoster)
            .filter(
                FantaRoster.player_id == inj.player_id,
                FantaRoster.season_id == season_id,
                FantaRoster.is_active == True,
            )
            .all()
        )
        teams = []
        for r in rosters:
            sub = next((s for s in r.temp_subs if s.injury_id == inj.id), None)
            teams.append({
                "roster_id": r.id,
                "team_id": r.fanta_team_id,
                "team_name": r.fanta_team.name,
                "league_level": r.fanta_team.league.level.value if r.fanta_team.league else None,
                "swaps_used": _swaps_used(db, r.fanta_team_id, season_id),
                "swap": _swap_payload(sub) if sub else None,
            })
        result.append({
            "injury_id": inj.id,
            "player_id": inj.player_id,
            "player_name": inj.player.name if inj.player else None,
            "role": inj.player.role if inj.player else None,
            "current_price": snap.price if snap else None,
            "is_active": inj.is_active,
            "created_at": inj.created_at,
            "teams": teams,
        })
    return {
        "max_swaps_per_team": MAX_SWAPS_PER_TEAM,
        "warning": _season_end_warning(db, season_id),
        "injuries": result,
    }


@router.get("/candidates")
def list_candidates(
    injury_id: int,
    team_id: int,
    search: str = "",
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    injury = db.query(InjuryPlayer).filter(InjuryPlayer.id == injury_id).first()
    team = db.query(FantaTeam).filter(FantaTeam.id == team_id).first()
    if not injury or not team:
        raise HTTPException(404)
    snap = _latest_snapshot(db, injury.player_id, injury.season_id)
    if not snap:
        raise HTTPException(400, "Quotazione attuale dell'infortunato non disponibile")
    term = search.strip()
    if len(term) < 2:
        return []

    latest = (
        db.query(PlayerSnapshot.player_id, func.max(PlayerSnapshot.match_day).label("md"))
        .filter(PlayerSnapshot.season_id == injury.season_id)
        .group_by(PlayerSnapshot.player_id)
        .subquery()
    )
    # Fuori dalla lega della squadra: giocatori gia' in una rosa attiva; fuori
    # in generale: infortunati attivi.
    taken = (
        db.query(FantaRoster.player_id)
        .join(FantaTeam, FantaTeam.id == FantaRoster.fanta_team_id)
        .filter(
            FantaRoster.season_id == injury.season_id,
            FantaRoster.is_active == True,
            FantaTeam.league_id == team.league_id,
        )
    )
    injured = db.query(InjuryPlayer.player_id).filter(
        InjuryPlayer.season_id == injury.season_id, InjuryPlayer.is_active == True
    )
    rows = (
        db.query(Player, PlayerSnapshot.price)
        .join(latest, latest.c.player_id == Player.id)
        .join(
            PlayerSnapshot,
            (PlayerSnapshot.player_id == Player.id)
            & (PlayerSnapshot.season_id == injury.season_id)
            & (PlayerSnapshot.match_day == latest.c.md),
        )
        .filter(
            Player.name.ilike(f"%{term}%"),
            PlayerSnapshot.price <= snap.price,
            Player.id.notin_(taken),
            Player.id.notin_(injured),
        )
        .order_by(Player.name)
        .limit(30)
        .all()
    )
    return [{"id": p.id, "name": p.name, "role": p.role, "price": price} for p, price in rows]


class SwapCreate(BaseModel):
    injury_id: int
    team_id: int
    replacement_player_id: int


@router.post("")
def create_swap(data: SwapCreate, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    injury = db.query(InjuryPlayer).filter(InjuryPlayer.id == data.injury_id).first()
    if not injury:
        raise HTTPException(404, "Infortunio non trovato")
    season_id = injury.season_id

    # Lock sulla squadra: serializza i cambi concorrenti cosi' il tetto non
    # si supera con due richieste simultanee.
    team = db.query(FantaTeam).filter(FantaTeam.id == data.team_id).with_for_update().first()
    if not team or team.season_id != season_id:
        raise HTTPException(404, "Squadra non trovata per la stagione dell'infortunio")

    roster = (
        db.query(FantaRoster)
        .filter(
            FantaRoster.fanta_team_id == team.id,
            FantaRoster.player_id == injury.player_id,
            FantaRoster.season_id == season_id,
            FantaRoster.is_active == True,
        )
        .first()
    )
    if not roster:
        raise HTTPException(400, "La squadra non ha questo giocatore in rosa attiva")
    if any(s.injury_id == injury.id for s in roster.temp_subs):
        raise HTTPException(409, "Cambio gia' registrato per questo infortunio")

    used = _swaps_used(db, team.id, season_id)
    if used >= MAX_SWAPS_PER_TEAM:
        raise HTTPException(409, f"La squadra ha gia' usato i {MAX_SWAPS_PER_TEAM} cambi disponibili in stagione")

    repl = db.query(Player).filter(Player.id == data.replacement_player_id).first()
    if not repl:
        raise HTTPException(404, "Sostituto non trovato")
    if repl.id == injury.player_id:
        raise HTTPException(400, "Il sostituto non puo' essere l'infortunato")

    injured_snap = _latest_snapshot(db, injury.player_id, season_id)
    repl_snap = _latest_snapshot(db, repl.id, season_id)
    if not injured_snap or not repl_snap:
        raise HTTPException(400, "Quotazione attuale non disponibile")
    if repl_snap.price > injured_snap.price:
        raise HTTPException(
            400,
            f"Il sostituto costa {repl_snap.price:g}, piu' dell'infortunato ({injured_snap.price:g})",
        )

    in_league = (
        db.query(FantaRoster.id)
        .join(FantaTeam, FantaTeam.id == FantaRoster.fanta_team_id)
        .filter(
            FantaRoster.player_id == repl.id,
            FantaRoster.season_id == season_id,
            FantaRoster.is_active == True,
            FantaTeam.league_id == team.league_id,
        )
        .first()
    )
    if in_league:
        raise HTTPException(400, "Il sostituto e' gia' in rosa a una squadra della stessa lega")
    if db.query(InjuryPlayer.id).filter(
        InjuryPlayer.player_id == repl.id, InjuryPlayer.season_id == season_id, InjuryPlayer.is_active == True
    ).first():
        raise HTTPException(400, "Il sostituto e' a sua volta infortunato")

    start_day = (
        db.query(func.max(PlayerSnapshot.match_day)).filter(PlayerSnapshot.season_id == season_id).scalar() or 0
    )
    sub = FantaRosterTempSub(
        roster_entry_id=roster.id,
        replacement_player_id=repl.id,
        start_match_day=start_day,
        injury_id=injury.id,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {**_swap_payload(sub), "swaps_used": used + 1, "warning": _season_end_warning(db, season_id)}


@router.delete("/{swap_id}")
def delete_swap(swap_id: int, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    sub = db.query(FantaRosterTempSub).filter(FantaRosterTempSub.id == swap_id).first()
    if not sub:
        raise HTTPException(404)
    db.delete(sub)
    db.commit()
    return {"ok": True}
