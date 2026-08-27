"""League, standings and competitions router."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.season import Season
from app.models.competition import Competition, CompetitionStanding, CompetitionType, MatchResult, CompetitionGroup, CompetitionGroupTeam, CompetitionPhase
from app.models.fanta_team import FantaTeam, League
from app.services.auth_service import require_admin

router = APIRouter(tags=["league"])

seasons_router = APIRouter(prefix="/seasons")
competitions_router = APIRouter(prefix="/competitions")

# Gold/Bronze/Carbon hanno l'iscrizione automatica tramite FantaTeam.league_id
# (stessa distinzione usata in frontend/.../admin-teams.component.ts).
MAIN_LEAGUE_TYPES = {"GOLD", "BRONZE", "CARBON"}


@seasons_router.get("")
def list_seasons(db: Session = Depends(get_db)):
    seasons = db.query(Season).order_by(Season.year_start.desc()).all()
    return [
        {"id": s.id, "label": s.label, "year_start": s.year_start,
         "year_end": s.year_end, "is_current": s.is_current}
        for s in seasons
    ]


@seasons_router.patch("/{season_id}/set-current")
def set_current_season(season_id: int, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(404, "Stagione non trovata")
    db.query(Season).filter(Season.is_current == True).update({"is_current": False})
    season.is_current = True
    db.commit()
    return {"ok": True, "id": season.id, "label": season.label}


@seasons_router.get("/{season_id}/leagues")
def get_season_leagues(season_id: int, db: Session = Depends(get_db)):
    leagues = db.query(League).filter(League.season_id == season_id).all()
    return [{"id": l.id, "level": l.level} for l in leagues]


@seasons_router.get("/{season_id}/competitions")
def get_season_competitions(season_id: int, db: Session = Depends(get_db)):
    comps = db.query(Competition).filter(Competition.season_id == season_id).all()
    return [
        {"id": c.id, "name": c.name, "type": c.type, "is_active": c.is_active}
        for c in comps
    ]


class CompetitionCreate(BaseModel):
    season_id: int
    type: str
    name: str | None = None


@competitions_router.post("", status_code=201)
def create_competition(data: CompetitionCreate, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    season = db.query(Season).filter(Season.id == data.season_id).first()
    if not season:
        raise HTTPException(404, "Stagione non trovata")
    comp_type = data.type.upper()
    if comp_type not in {t.value for t in CompetitionType}:
        raise HTTPException(400, f"Tipo competizione non valido: {data.type}")

    existing = db.query(Competition).filter(
        Competition.season_id == data.season_id, Competition.type == comp_type
    ).first()
    if existing:
        raise HTTPException(400, f"Esiste già una competizione {comp_type} per questa stagione")

    # Gold/Bronze/Carbon hanno iscrizione automatica via League: se manca la
    # lega di quel livello per la stagione, la creo insieme alla competizione
    # (altrimenti la competizione risulterebbe senza nessuna squadra eleggibile).
    if comp_type in MAIN_LEAGUE_TYPES:
        league = db.query(League).filter(
            League.season_id == data.season_id, League.level == comp_type
        ).first()
        if not league:
            league = League(season_id=data.season_id, level=comp_type)
            db.add(league)
            db.flush()

    comp = Competition(
        season_id=data.season_id, type=comp_type,
        name=data.name or f"{comp_type.capitalize()} {season.label}",
    )
    db.add(comp)
    db.commit()
    return {"id": comp.id, "name": comp.name, "type": comp.type, "is_active": comp.is_active}


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
    # Silver e' la classifica ad accumulo (total_score), non a punti (pts).
    order_field = CompetitionStanding.total_score if comp_type and comp_type.upper() == "SILVER" else CompetitionStanding.pts
    standings = q.order_by(order_field.desc()).all()
    return [
        {
            "fanta_team_id": s.fanta_team_id,
            "fanta_team_name": s.fanta_team.name,
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
    comp = db.query(Competition).filter(Competition.id == comp_id).first()
    if not comp:
        raise HTTPException(404, "Competizione non trovata")
    q = db.query(CompetitionStanding).filter(CompetitionStanding.competition_id == comp_id)
    if match_day:
        q = q.filter(CompetitionStanding.match_day == match_day)
    # Silver e' la classifica ad accumulo (total_score), non a punti (pts).
    order_field = CompetitionStanding.total_score if comp.type.value == "SILVER" else CompetitionStanding.pts
    standings = q.order_by(CompetitionStanding.match_day, order_field.desc()).all()
    return [
        {
            "fanta_team_id": s.fanta_team_id, "match_day": s.match_day,
            "pts": s.pts, "wins": s.wins, "draws": s.draws, "losses": s.losses,
            "goals_for": s.goals_for, "goals_against": s.goals_against,
            "total_score": s.total_score,
        }
        for s in standings
    ]


def _standings_roster(db: Session, comp: Competition) -> list[FantaTeam]:
    """Squadre eleggibili per una competizione: automatiche via league_id per
    Gold/Bronze/Carbon, iscritte a mano (CompetitionGroupTeam) per le altre."""
    if comp.type.value in MAIN_LEAGUE_TYPES:
        return (
            db.query(FantaTeam)
            .join(League, League.id == FantaTeam.league_id)
            .filter(FantaTeam.season_id == comp.season_id, League.level == comp.type.value)
            .order_by(FantaTeam.name)
            .all()
        )
    return (
        db.query(FantaTeam)
        .join(CompetitionGroupTeam, CompetitionGroupTeam.fanta_team_id == FantaTeam.id)
        .join(CompetitionGroup, CompetitionGroup.id == CompetitionGroupTeam.group_id)
        .filter(CompetitionGroup.competition_id == comp.id)
        .order_by(FantaTeam.name)
        .all()
    )


@competitions_router.get("/{comp_id}/standings-editor")
def get_standings_editor(comp_id: int, match_day: int = 1, db: Session = Depends(get_db)):
    """Roster eleggibile + classifica corrente (se esiste) per una giornata,
    pensato per l'editor manuale in Gestione Squadre."""
    comp = db.query(Competition).filter(Competition.id == comp_id).first()
    if not comp:
        raise HTTPException(404, "Competizione non trovata")

    roster = _standings_roster(db, comp)
    standings_by_team = {
        s.fanta_team_id: s
        for s in db.query(CompetitionStanding).filter(
            CompetitionStanding.competition_id == comp_id,
            CompetitionStanding.match_day == match_day,
        )
    }
    result = []
    for t in roster:
        s = standings_by_team.get(t.id)
        result.append({
            "fanta_team_id": t.id,
            "fanta_team_name": t.name,
            "match_day": match_day,
            "pts": s.pts if s else 0,
            "total_score": s.total_score if s else 0.0,
            "wins": s.wins if s else 0,
            "draws": s.draws if s else 0,
            "losses": s.losses if s else 0,
            "goals_for": s.goals_for if s else 0.0,
            "goals_against": s.goals_against if s else 0.0,
        })
    return result


class StandingUpsert(BaseModel):
    fanta_team_id: int
    match_day: int = 1
    pts: int | None = None
    total_score: float | None = None
    wins: int | None = None
    draws: int | None = None
    losses: int | None = None
    goals_for: float | None = None
    goals_against: float | None = None


@competitions_router.put("/{comp_id}/standings")
def upsert_standing(
    comp_id: int, data: StandingUpsert, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
):
    comp = db.query(Competition).filter(Competition.id == comp_id).first()
    if not comp:
        raise HTTPException(404, "Competizione non trovata")
    team = db.query(FantaTeam).filter(FantaTeam.id == data.fanta_team_id).first()
    if not team or team.season_id != comp.season_id:
        raise HTTPException(400, "La squadra scelta non appartiene alla stagione della competizione")

    standing = (
        db.query(CompetitionStanding)
        .filter(
            CompetitionStanding.competition_id == comp_id,
            CompetitionStanding.fanta_team_id == data.fanta_team_id,
            CompetitionStanding.match_day == data.match_day,
        )
        .first()
    )
    if not standing:
        standing = CompetitionStanding(
            competition_id=comp_id, fanta_team_id=data.fanta_team_id, match_day=data.match_day
        )
        db.add(standing)

    for field in ("pts", "total_score", "wins", "draws", "losses", "goals_for", "goals_against"):
        value = getattr(data, field)
        if value is not None:
            setattr(standing, field, value)

    db.commit()
    return {"ok": True}


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


@competitions_router.get("/{comp_id}/bracket")
def get_competition_bracket(comp_id: int, db: Session = Depends(get_db)):
    """Vista per le coppe (Ciempions/UEFA/Coppa Italia): classifica calcolata
    al volo per ogni girone dai risultati (nessuna CompetitionStanding viene
    salvata per le coppe, a differenza dei campionati principali) + tabellone
    della fase a eliminazione con gli accoppiamenti (andata/ritorno o gara
    singola per la finale) raggruppati per fase."""
    comp = db.query(Competition).filter(Competition.id == comp_id).first()
    if not comp:
        raise HTTPException(404, "Competizione non trovata")

    teams_by_id = {t.id: t for t in db.query(FantaTeam).filter(FantaTeam.season_id == comp.season_id)}
    matches = db.query(MatchResult).filter(MatchResult.competition_id == comp_id).all()

    groups_out = []
    for group in db.query(CompetitionGroup).filter(CompetitionGroup.competition_id == comp_id).order_by(CompetitionGroup.name):
        team_ids = {
            row[0] for row in
            db.query(CompetitionGroupTeam.fanta_team_id).filter(CompetitionGroupTeam.group_id == group.id)
        }
        if not team_ids:
            continue
        def team_name(tid: int) -> str:
            team = teams_by_id.get(tid)
            return team.name if team else f"Squadra #{tid}"

        stats = {
            tid: {"fanta_team_id": tid, "name": team_name(tid),
                  "played": 0, "wins": 0, "draws": 0, "losses": 0, "goals_for": 0, "goals_against": 0, "pts": 0}
            for tid in team_ids
        }
        for m in matches:
            if m.phase != CompetitionPhase.GROUP:
                continue
            if m.fanta_team_home_id not in team_ids or m.fanta_team_away_id not in team_ids:
                continue
            home, away = stats[m.fanta_team_home_id], stats[m.fanta_team_away_id]
            home["played"] += 1
            away["played"] += 1
            home["goals_for"] += m.goals_home
            home["goals_against"] += m.goals_away
            away["goals_for"] += m.goals_away
            away["goals_against"] += m.goals_home
            home["pts"] += m.pts_home
            away["pts"] += m.pts_away
            if m.pts_home > m.pts_away:
                home["wins"] += 1
                away["losses"] += 1
            elif m.pts_home < m.pts_away:
                away["wins"] += 1
                home["losses"] += 1
            else:
                home["draws"] += 1
                away["draws"] += 1
        standings = sorted(
            stats.values(),
            key=lambda s: (s["pts"], s["goals_for"] - s["goals_against"], s["goals_for"]),
            reverse=True,
        )
        groups_out.append({"name": group.name, "standings": standings})

    knockout_matches = [m for m in matches if m.phase != CompetitionPhase.GROUP]
    phase_order = [CompetitionPhase.ROUND_OF_16, CompetitionPhase.QUARTER_FINAL,
                   CompetitionPhase.SEMI_FINAL, CompetitionPhase.FINAL]
    knockout_out = []
    for phase in phase_order:
        phase_matches = sorted((m for m in knockout_matches if m.phase == phase), key=lambda m: m.match_day)
        if not phase_matches:
            continue
        ties: dict[frozenset, dict] = {}
        for m in phase_matches:
            key = frozenset((m.fanta_team_home_id, m.fanta_team_away_id))
            tie = ties.setdefault(key, {"legs": [], "goals_by_team": {}})
            tie["legs"].append({
                "match_day": m.match_day,
                "home_team_id": m.fanta_team_home_id, "away_team_id": m.fanta_team_away_id,
                "score_home": m.score_home, "score_away": m.score_away,
                "goals_home": m.goals_home, "goals_away": m.goals_away,
            })
            goals_by_team = tie["goals_by_team"]
            goals_by_team[m.fanta_team_home_id] = goals_by_team.get(m.fanta_team_home_id, 0) + m.goals_home
            goals_by_team[m.fanta_team_away_id] = goals_by_team.get(m.fanta_team_away_id, 0) + m.goals_away

        tie_list = []
        for key, tie in ties.items():
            team_ids = list(key)
            a_id, b_id = team_ids[0], (team_ids[1] if len(team_ids) > 1 else team_ids[0])
            goals_a = tie["goals_by_team"].get(a_id, 0)
            goals_b = tie["goals_by_team"].get(b_id, 0)
            winner_id = a_id if goals_a > goals_b else (b_id if goals_b > goals_a else None)
            tie_list.append({
                "team_a_id": a_id, "team_a_name": teams_by_id[a_id].name if a_id in teams_by_id else f"Squadra #{a_id}",
                "team_b_id": b_id, "team_b_name": teams_by_id[b_id].name if b_id in teams_by_id else f"Squadra #{b_id}",
                "legs": sorted(tie["legs"], key=lambda l: l["match_day"]),
                "aggregate_a": goals_a, "aggregate_b": goals_b, "winner_id": winner_id,
            })
        knockout_out.append({"phase": phase, "ties": tie_list})

    return {"groups": groups_out, "knockout": knockout_out}


class ParticipantAdd(BaseModel):
    fanta_team_id: int


_DEFAULT_GROUP_NAME = "Girone Unico"


@competitions_router.get("/{comp_id}/participants")
def get_competition_participants(comp_id: int, db: Session = Depends(get_db)):
    comp = db.query(Competition).filter(Competition.id == comp_id).first()
    if not comp:
        raise HTTPException(404, "Competizione non trovata")

    participant_ids = {
        row[0]
        for row in (
            db.query(CompetitionGroupTeam.fanta_team_id)
            .join(CompetitionGroup, CompetitionGroup.id == CompetitionGroupTeam.group_id)
            .filter(CompetitionGroup.competition_id == comp_id)
            .all()
        )
    }
    season_teams = db.query(FantaTeam).filter(FantaTeam.season_id == comp.season_id).order_by(FantaTeam.name).all()

    return {
        "participants": [
            {"id": t.id, "name": t.name} for t in season_teams if t.id in participant_ids
        ],
        "available": [
            {"id": t.id, "name": t.name} for t in season_teams if t.id not in participant_ids
        ],
    }


@competitions_router.post("/{comp_id}/participants", status_code=201)
def add_competition_participant(
    comp_id: int, data: ParticipantAdd, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
):
    comp = db.query(Competition).filter(Competition.id == comp_id).first()
    if not comp:
        raise HTTPException(404, "Competizione non trovata")
    team = db.query(FantaTeam).filter(FantaTeam.id == data.fanta_team_id).first()
    if not team or team.season_id != comp.season_id:
        raise HTTPException(400, "La squadra scelta non appartiene alla stagione della competizione")

    group = (
        db.query(CompetitionGroup)
        .filter(CompetitionGroup.competition_id == comp_id, CompetitionGroup.name == _DEFAULT_GROUP_NAME)
        .first()
    )
    if not group:
        group = CompetitionGroup(competition_id=comp_id, name=_DEFAULT_GROUP_NAME)
        db.add(group)
        db.flush()

    existing = (
        db.query(CompetitionGroupTeam)
        .filter(CompetitionGroupTeam.group_id == group.id, CompetitionGroupTeam.fanta_team_id == data.fanta_team_id)
        .first()
    )
    if not existing:
        db.add(CompetitionGroupTeam(group_id=group.id, fanta_team_id=data.fanta_team_id))
        db.commit()
    return {"ok": True}


@competitions_router.delete("/{comp_id}/participants/{fanta_team_id}")
def remove_competition_participant(
    comp_id: int, fanta_team_id: int, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
):
    deleted = (
        db.query(CompetitionGroupTeam)
        .filter(
            CompetitionGroupTeam.fanta_team_id == fanta_team_id,
            CompetitionGroupTeam.group_id.in_(
                db.query(CompetitionGroup.id).filter(CompetitionGroup.competition_id == comp_id)
            ),
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    if not deleted:
        raise HTTPException(404, "Squadra non iscritta a questa competizione")
    return {"ok": True}


router.include_router(seasons_router)
router.include_router(competitions_router)
