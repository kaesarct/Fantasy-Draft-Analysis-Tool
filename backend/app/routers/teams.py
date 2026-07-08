"""Fanta-teams and allenatori routers."""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.fanta_allenatore import FantaAllenatore
from app.models.fanta_team import FantaTeam, FantaTeamCoach, FantaRoster, League

router = APIRouter(tags=["teams"])


class AllenatoreCreate(BaseModel):
    username: str
    display_name: str
    email: str | None = None


class AllenatoreUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None
    is_active: bool | None = None


class CoachAssign(BaseModel):
    allenatore_id: int
    is_primary: bool = True


# ── FantaAllenatori ─────────────────────────────────────────────────────────
allenatori_router = APIRouter(prefix="/allenatori")


@allenatori_router.get("")
def list_allenatori(db: Session = Depends(get_db)):
    al = db.query(FantaAllenatore).order_by(FantaAllenatore.display_name).all()
    return [
        {"id": a.id, "username": a.username, "display_name": a.display_name, "is_active": a.is_active}
        for a in al
    ]


@allenatori_router.post("", status_code=201)
def create_allenatore(data: AllenatoreCreate, db: Session = Depends(get_db)):
    username = data.username.strip()
    if not username or not data.display_name.strip():
        raise HTTPException(400, "username e display_name sono obbligatori")
    if db.query(FantaAllenatore).filter(FantaAllenatore.username.ilike(username)).first():
        raise HTTPException(409, f"Username '{username}' gia' esistente")
    a = FantaAllenatore(
        username=username,
        display_name=data.display_name.strip(),
        email=data.email.strip() if data.email else None,
    )
    db.add(a)
    db.commit()
    return {"id": a.id, "username": a.username, "display_name": a.display_name, "is_active": a.is_active}


@allenatori_router.patch("/{al_id}")
def update_allenatore(al_id: int, data: AllenatoreUpdate, db: Session = Depends(get_db)):
    a = db.query(FantaAllenatore).filter(FantaAllenatore.id == al_id).first()
    if not a:
        raise HTTPException(404, "Allenatore not found")
    if data.display_name is not None:
        a.display_name = data.display_name.strip()
    if data.email is not None:
        a.email = data.email.strip() or None
    if data.is_active is not None:
        a.is_active = data.is_active
    db.commit()
    return {"id": a.id, "username": a.username, "display_name": a.display_name, "is_active": a.is_active}


@allenatori_router.get("/{al_id}")
def get_allenatore(al_id: int, db: Session = Depends(get_db)):
    a = db.query(FantaAllenatore).filter(FantaAllenatore.id == al_id).first()
    if not a:
        raise HTTPException(404, "Allenatore not found")
    teams = [
        {
            "team_id": tc.fanta_team.id,
            "team_name": tc.fanta_team.name,
            "season": tc.fanta_team.season.label if tc.fanta_team.season else None,
            "league": tc.fanta_team.league.level if tc.fanta_team.league else None,
            "is_primary": tc.is_primary,
        }
        for tc in a.team_coaches
    ]
    return {
        "id": a.id, "username": a.username, "display_name": a.display_name,
        "email": a.email, "is_active": a.is_active, "teams": teams,
    }


# ── FantaTeams ──────────────────────────────────────────────────────────────
teams_router = APIRouter(prefix="/fanta-teams")


@teams_router.get("")
def list_fanta_teams(
    season_id: int | None = None,
    league_level: str | None = None,
    db: Session = Depends(get_db),
):
    q = (
        db.query(FantaTeam)
        .options(joinedload(FantaTeam.logos), joinedload(FantaTeam.coaches))
    )
    if season_id:
        q = q.filter(FantaTeam.season_id == season_id)
    if league_level:
        leagues = db.query(League).filter(League.level == league_level.upper()).all()
        league_ids = [l.id for l in leagues]
        q = q.filter(FantaTeam.league_id.in_(league_ids))
    teams = q.all()
    return [_team_summary(t) for t in teams]


@teams_router.get("/{team_id}")
def get_fanta_team(team_id: int, db: Session = Depends(get_db)):
    t = db.query(FantaTeam).filter(FantaTeam.id == team_id).first()
    if not t:
        raise HTTPException(404, "Team not found")
    roster = db.query(FantaRoster).filter(
        FantaRoster.fanta_team_id == team_id,
        FantaRoster.is_active == True,
    ).all()
    return {
        **_team_summary(t),
        "roster": [
            {
                "player_id": r.player_id,
                "player_name": r.player.name if r.player else None,
                "role": r.player.role if r.player else None,
                "purchase_price": r.purchase_price,
            }
            for r in roster
        ],
    }


@teams_router.post("/{team_id}/coaches", status_code=201)
def assign_coach(team_id: int, data: CoachAssign, db: Session = Depends(get_db)):
    team = db.query(FantaTeam).filter(FantaTeam.id == team_id).first()
    if not team:
        raise HTTPException(404, "Team not found")
    allenatore = db.query(FantaAllenatore).filter(FantaAllenatore.id == data.allenatore_id).first()
    if not allenatore:
        raise HTTPException(404, "Allenatore not found")

    if data.is_primary:
        # Un solo allenatore primario per squadra.
        db.query(FantaTeamCoach).filter(
            FantaTeamCoach.fanta_team_id == team_id,
            FantaTeamCoach.is_primary == True,
        ).update({FantaTeamCoach.is_primary: False})

    link = (
        db.query(FantaTeamCoach)
        .filter(
            FantaTeamCoach.fanta_team_id == team_id,
            FantaTeamCoach.allenatore_id == data.allenatore_id,
        )
        .first()
    )
    if link:
        link.is_primary = data.is_primary
    else:
        db.add(FantaTeamCoach(
            fanta_team_id=team_id, allenatore_id=data.allenatore_id, is_primary=data.is_primary
        ))
    db.commit()
    return {"ok": True, "team_id": team_id, "allenatore_id": data.allenatore_id, "is_primary": data.is_primary}


@teams_router.delete("/{team_id}/coaches/{allenatore_id}")
def remove_coach(team_id: int, allenatore_id: int, db: Session = Depends(get_db)):
    link = (
        db.query(FantaTeamCoach)
        .filter(
            FantaTeamCoach.fanta_team_id == team_id,
            FantaTeamCoach.allenatore_id == allenatore_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(404, "Associazione non trovata")
    db.delete(link)
    db.commit()
    return {"ok": True}


def _team_summary(t: FantaTeam):
    logo = next(
        (l.logo_url for l in t.logos if l.season_id == t.season_id), None
    )
    coaches = [
        {"id": tc.allenatore.id, "name": tc.allenatore.display_name, "primary": tc.is_primary}
        for tc in t.coaches
    ]
    return {
        "id": t.id, "name": t.name, "season_id": t.season_id,
        "league_id": t.league_id, "credits_spent": t.credits_spent,
        "remaining_credits": t.remaining_credits, "logo_url": logo,
        "coaches": coaches,
    }


router.include_router(allenatori_router)
router.include_router(teams_router)
