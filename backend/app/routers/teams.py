"""Fanta-teams and allenatori routers."""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.fanta_allenatore import FantaAllenatore
from app.models.fanta_team import FantaTeam, FantaTeamCoach, FantaRoster, League, FantaTeamLineage
from app.models.competition import (
    Competition, CompetitionStanding, MatchResult, CompetitionGroup, CompetitionGroupTeam, CompetitionPhase,
)
from app.services.auth_service import require_admin
from app.routers.league import MAIN_LEAGUE_TYPES
from app.routers.team_merge import _SIMPLE_TABLES, _UNIQUE_TABLES

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


class FantaTeamCreate(BaseModel):
    name: str
    season_id: int
    league_id: int


class FantaTeamUpdate(BaseModel):
    name: str | None = None
    league_id: int | None = None


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
def create_allenatore(data: AllenatoreCreate, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
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


def _group_rank_for_team(
    db: Session, comp: Competition, matches: list[MatchResult], team_id: int
) -> dict | None:
    """Piazzamento nel proprio girone (stessa logica di get_competition_bracket
    in league.py) — usato solo come ripiego quando una coppa non ha ancora
    nessuna partita a eliminazione diretta (fase a gironi in corso)."""
    group_link = (
        db.query(CompetitionGroupTeam)
        .join(CompetitionGroup, CompetitionGroup.id == CompetitionGroupTeam.group_id)
        .filter(CompetitionGroup.competition_id == comp.id, CompetitionGroupTeam.fanta_team_id == team_id)
        .first()
    )
    if not group_link:
        return None
    group_team_ids = {
        row[0] for row in db.query(CompetitionGroupTeam.fanta_team_id)
        .filter(CompetitionGroupTeam.group_id == group_link.group_id)
    }
    stats = {tid: {"pts": 0, "gf": 0, "ga": 0} for tid in group_team_ids}
    for m in matches:
        if m.phase != CompetitionPhase.GROUP:
            continue
        if m.fanta_team_home_id not in group_team_ids or m.fanta_team_away_id not in group_team_ids:
            continue
        h, a = stats[m.fanta_team_home_id], stats[m.fanta_team_away_id]
        h["gf"] += m.goals_home; h["ga"] += m.goals_away
        a["gf"] += m.goals_away; a["ga"] += m.goals_home
        h["pts"] += m.pts_home; a["pts"] += m.pts_away
    ranked = sorted(
        group_team_ids,
        key=lambda tid: (stats[tid]["pts"], stats[tid]["gf"] - stats[tid]["ga"], stats[tid]["gf"]),
        reverse=True,
    )
    return {"rank": ranked.index(team_id) + 1, "total_teams": len(ranked)}


def _cup_standing_for_team(db: Session, comp: Competition, team_id: int) -> dict | None:
    """Piazzamento sintetico per una coppa (gironi + eliminazione diretta),
    calcolato al volo dai MatchResult — usato quando la competizione non ha
    righe CompetitionStanding salvate (il caso normale per Ciempions/UEFA/
    Coppa Italia/Eurocup: il tabellone si calcola sempre dal vivo, mai
    persistito in classifica, vedi get_competition_bracket in league.py).

    Convenzione di piazzamento per l'eliminazione diretta (nessun dato
    "ufficiale" esiste per una graduatoria di coppa, quindi ne serve una
    convenzionale): vincitore=1°, finalista perdente=2°, poi a scalare a pari
    merito per fase persa (semifinalisti, quartifinalisti, ecc.); chi non ha
    mai raggiunto l'eliminazione diretta resta a pari merito subito sotto
    l'ultima fase conosciuta. total_teams = tutte le squadre della coppa
    (gironi + eliminazione), non solo il proprio girone."""
    matches = db.query(MatchResult).filter(MatchResult.competition_id == comp.id).all()
    if not matches:
        return None

    all_team_ids: set[int] = set()
    for m in matches:
        all_team_ids.add(m.fanta_team_home_id)
        all_team_ids.add(m.fanta_team_away_id)
    for row in (
        db.query(CompetitionGroupTeam.fanta_team_id)
        .join(CompetitionGroup, CompetitionGroup.id == CompetitionGroupTeam.group_id)
        .filter(CompetitionGroup.competition_id == comp.id)
    ):
        all_team_ids.add(row[0])

    if team_id not in all_team_ids:
        return None
    total_teams = len(all_team_ids)

    knockout_matches = [m for m in matches if m.phase != CompetitionPhase.GROUP]
    phase_order = [
        CompetitionPhase.ROUND_OF_16, CompetitionPhase.QUARTER_FINAL,
        CompetitionPhase.SEMI_FINAL, CompetitionPhase.FINAL,
    ]

    # Ultima fase raggiunta da ogni squadra (viene sovrascritta a ogni fase
    # superata, quindi a fine ciclo contiene la fase più avanzata di ognuna).
    last_phase: dict[int, CompetitionPhase] = {}
    won_final: dict[int, bool] = {}
    for phase in phase_order:
        ties: dict[frozenset, dict] = {}
        for m in knockout_matches:
            if m.phase != phase:
                continue
            key = frozenset((m.fanta_team_home_id, m.fanta_team_away_id))
            goals = ties.setdefault(key, {})
            goals[m.fanta_team_home_id] = goals.get(m.fanta_team_home_id, 0) + m.goals_home
            goals[m.fanta_team_away_id] = goals.get(m.fanta_team_away_id, 0) + m.goals_away
        for key, goals in ties.items():
            for tid in key:
                last_phase[tid] = phase
            if phase == CompetitionPhase.FINAL and len(key) == 2:
                a, b = tuple(key)
                if goals.get(a, 0) != goals.get(b, 0):
                    winner = a if goals.get(a, 0) > goals.get(b, 0) else b
                    won_final[winner] = True

    if not last_phase:
        # Nessuna partita a eliminazione diretta ancora giocata: usa il
        # piazzamento nel proprio girone invece di dichiarare tutti "1°".
        return _group_rank_for_team(db, comp, matches, team_id)

    rank_by_team: dict[int, int] = {}
    cumulative = 0
    for phase in reversed(phase_order):
        teams_in_phase = [tid for tid, p in last_phase.items() if p == phase]
        if not teams_in_phase:
            continue
        if phase == CompetitionPhase.FINAL:
            winner = next((tid for tid in teams_in_phase if won_final.get(tid)), None)
            others = [tid for tid in teams_in_phase if tid != winner]
            if winner is not None:
                rank_by_team[winner] = 1
                cumulative = 1
            if others:
                tier_rank = cumulative + 1
                for tid in others:
                    rank_by_team[tid] = tier_rank
                cumulative += len(others)
        else:
            tier_rank = cumulative + 1
            for tid in teams_in_phase:
                rank_by_team[tid] = tier_rank
            cumulative += len(teams_in_phase)

    if team_id in rank_by_team:
        return {"rank": rank_by_team[team_id], "total_teams": total_teams}
    # Mai arrivata all'eliminazione diretta: pari merito subito sotto l'ultima
    # fase conosciuta (es. sotto gli ottavi, se esistono).
    return {"rank": cumulative + 1, "total_teams": total_teams}


def _team_standings_summary(db: Session, team: FantaTeam) -> list[dict]:
    """Piazzamento di una squadra in ciascuna competizione a cui ha
    partecipato (ultima giornata registrata). is_partial_data=True quando
    nessuna squadra della competizione ha "played" valorizzato: significa
    che quella stagione non ha una classifica reale, solo un piazzamento
    noto (es. solo il vincitore) inserito come valore puramente ordinale —
    le altre posizioni in quel caso non sono da considerare affidabili."""
    result = []
    seen_comp_ids: set[int] = set()

    standings = db.query(CompetitionStanding).filter(CompetitionStanding.fanta_team_id == team.id).all()
    latest_by_comp: dict[int, CompetitionStanding] = {}
    for s in standings:
        cur = latest_by_comp.get(s.competition_id)
        if not cur or s.match_day > cur.match_day:
            latest_by_comp[s.competition_id] = s

    for comp_id, s in latest_by_comp.items():
        comp = db.query(Competition).filter(Competition.id == comp_id).first()
        if not comp:
            continue
        seen_comp_ids.add(comp_id)
        all_rows = db.query(CompetitionStanding).filter(
            CompetitionStanding.competition_id == comp_id,
            CompetitionStanding.match_day == s.match_day,
        ).all()
        is_silver = comp.type == "SILVER"
        ranked = sorted(all_rows, key=lambda r: (r.total_score if is_silver else r.pts), reverse=True)
        rank = next((i + 1 for i, r in enumerate(ranked) if r.fanta_team_id == team.id), None)
        result.append({
            "competition_id": comp_id,
            "competition_type": comp.type,
            "rank": rank,
            "total_teams": len(ranked),
            "is_partial_data": all((r.played or 0) == 0 for r in all_rows),
        })

    # Coppe senza CompetitionStanding salvata (il caso normale: il tabellone
    # di Ciempions/UEFA/Coppa Italia/Eurocup si calcola sempre al volo dai
    # MatchResult, mai persistito in classifica) — calcolate qui allo stesso
    # modo del tabellone live.
    other_comps = (
        db.query(Competition)
        .filter(Competition.season_id == team.season_id, ~Competition.id.in_(seen_comp_ids))
        .all()
    )
    for comp in other_comps:
        if comp.type in MAIN_LEAGUE_TYPES or comp.type == "SILVER":
            continue
        cup_result = _cup_standing_for_team(db, comp, team.id)
        if cup_result:
            result.append({
                "competition_id": comp.id,
                "competition_type": comp.type,
                "rank": cup_result["rank"],
                "total_teams": cup_result["total_teams"],
                "is_partial_data": False,
            })

    return result


@allenatori_router.get("/{al_id}")
def get_allenatore(al_id: int, db: Session = Depends(get_db)):
    a = db.query(FantaAllenatore).filter(FantaAllenatore.id == al_id).first()
    if not a:
        raise HTTPException(404, "Allenatore not found")
    teams = [
        {
            "team_id": tc.fanta_team.id,
            "team_name": tc.fanta_team.name,
            "season_id": tc.fanta_team.season_id,
            "season": tc.fanta_team.season.label if tc.fanta_team.season else None,
            "league": tc.fanta_team.league.level if tc.fanta_team.league else None,
            "is_primary": tc.is_primary,
            "standings": _team_standings_summary(db, tc.fanta_team),
        }
        for tc in a.team_coaches
    ]
    teams.sort(key=lambda t: t["season_id"] or 0)
    return {
        "id": a.id, "username": a.username, "display_name": a.display_name,
        "email": a.email, "is_active": a.is_active, "teams": teams,
    }


@allenatori_router.get("/{al_id}/players")
def get_allenatore_players(al_id: int, season_id: int | None = None, db: Session = Depends(get_db)):
    """Tutti i giocatori acquistati nel corso degli anni da una qualsiasi
    delle squadre gestite da questo allenatore, raggruppati per giocatore —
    con la lista delle quotazioni pagate ogni volta che e' stato acquistato
    (anche piu' volte in stagioni diverse)."""
    a = db.query(FantaAllenatore).filter(FantaAllenatore.id == al_id).first()
    if not a:
        raise HTTPException(404, "Allenatore not found")

    team_ids = [tc.fanta_team_id for tc in a.team_coaches]
    if not team_ids:
        return []

    q = db.query(FantaRoster).filter(FantaRoster.fanta_team_id.in_(team_ids))
    if season_id:
        q = q.filter(FantaRoster.season_id == season_id)
    rows = q.all()
    if not rows:
        return []

    teams_by_id = {
        t.id: t for t in db.query(FantaTeam).filter(FantaTeam.id.in_(team_ids)).all()
    }

    by_player: dict[int, dict] = {}
    for r in rows:
        entry = by_player.setdefault(r.player_id, {
            "player_id": r.player_id,
            "player_name": r.player.name if r.player else None,
            "role": r.player.role if r.player else None,
            "acquisitions": [],
        })
        team = teams_by_id.get(r.fanta_team_id)
        entry["acquisitions"].append({
            "season_id": r.season_id,
            "season_label": team.season.label if team and team.season else None,
            "team_id": r.fanta_team_id,
            "team_name": team.name if team else None,
            "purchase_price": r.purchase_price,
            "is_active": r.is_active,
        })

    result = list(by_player.values())
    for entry in result:
        entry["acquisitions"].sort(key=lambda x: x["season_id"] or 0)
        entry["times_acquired"] = len(entry["acquisitions"])
    result.sort(key=lambda e: e["player_name"] or "")
    return result


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
        .options(joinedload(FantaTeam.logos), joinedload(FantaTeam.coaches), joinedload(FantaTeam.season))
    )
    if season_id:
        q = q.filter(FantaTeam.season_id == season_id)
    if league_level:
        leagues = db.query(League).filter(League.level == league_level.upper()).all()
        league_ids = [l.id for l in leagues]
        q = q.filter(FantaTeam.league_id.in_(league_ids))
    teams = q.all()
    return [_team_summary(t) for t in teams]


@teams_router.post("", status_code=201)
def create_fanta_team(data: FantaTeamCreate, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    name = data.name.strip()
    if not name:
        raise HTTPException(400, "Il nome e' obbligatorio")
    league = db.query(League).filter(League.id == data.league_id).first()
    if not league or league.season_id != data.season_id:
        raise HTTPException(400, "La lega scelta non appartiene alla stagione indicata")
    team = FantaTeam(name=name, season_id=data.season_id, league_id=data.league_id)
    db.add(team)
    db.commit()
    return _team_summary(team)


@teams_router.patch("/{team_id}")
def update_fanta_team(team_id: int, data: FantaTeamUpdate, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    team = db.query(FantaTeam).filter(FantaTeam.id == team_id).first()
    if not team:
        raise HTTPException(404, "Team not found")
    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(400, "Il nome non puo' essere vuoto")
        team.name = name
    if data.league_id is not None:
        league = db.query(League).filter(League.id == data.league_id).first()
        if not league or league.season_id != team.season_id:
            raise HTTPException(400, "La lega scelta non appartiene alla stagione della squadra")
        team.league_id = data.league_id
    db.commit()
    return _team_summary(team)


@teams_router.delete("/{team_id}")
def delete_fanta_team(team_id: int, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    team = db.query(FantaTeam).filter(FantaTeam.id == team_id).first()
    if not team:
        raise HTTPException(404, "Team not found")

    references: dict[str, int] = {}
    for model, fk_field in _SIMPLE_TABLES:
        count = db.query(model).filter(getattr(model, fk_field) == team_id).count()
        if count:
            references[f"{model.__tablename__}.{fk_field}"] = count
    for model, fk_field, _keys in _UNIQUE_TABLES:
        count = db.query(model).filter(getattr(model, fk_field) == team_id).count()
        if count:
            references[model.__tablename__] = references.get(model.__tablename__, 0) + count

    if references:
        raise HTTPException(
            409,
            detail={
                "message": "Squadra non eliminabile: ha ancora dati collegati. Usa l'unione invece della cancellazione.",
                "references": references,
            },
        )

    db.delete(team)
    db.commit()
    return {"ok": True}


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
        "standings": _team_standings_summary(db, t),
        "roster": [
            {
                "player_id": r.player_id,
                "player_name": r.player.name if r.player else None,
                "role": r.role or (r.player.role if r.player else None),
                "purchase_price": r.purchase_price,
            }
            for r in roster
        ],
    }


@teams_router.get("/{team_id}/roster-history")
def get_roster_history(team_id: int, db: Session = Depends(get_db)):
    """Movimenti di mercato della stagione (acquisti/svincoli) raggruppati
    per data — utile per distinguere la rosa iniziale (asta estiva) dai
    cambi di un successivo mercato di riparazione."""
    team = db.query(FantaTeam).filter(FantaTeam.id == team_id).first()
    if not team:
        raise HTTPException(404, "Team not found")

    rows = db.query(FantaRoster).filter(FantaRoster.fanta_team_id == team_id).all()
    events: dict[str, dict] = {}

    def _event(dt) -> dict:
        key = dt.date().isoformat() if dt else "sconosciuta"
        return events.setdefault(key, {"date": key, "acquired": [], "released": []})

    for r in rows:
        player_name = r.player.name if r.player else None
        role = r.role or (r.player.role if r.player else None)
        _event(r.acquired_at)["acquired"].append({
            "player_id": r.player_id, "player_name": player_name, "role": role, "price": r.purchase_price,
        })
        if r.released_at:
            _event(r.released_at)["released"].append({
                "player_id": r.player_id, "player_name": player_name, "role": role, "refund": r.purchase_price,
            })

    result = sorted(events.values(), key=lambda e: e["date"])
    for e in result:
        credit_spent = sum(p["price"] for p in e["acquired"])
        credit_refund = sum(p["refund"] for p in e["released"])
        e["credit_spent"] = credit_spent
        e["credit_refund"] = credit_refund
        e["credit_delta"] = credit_refund - credit_spent
    return result


@teams_router.get("/{team_id}/lineage")
def get_team_lineage(team_id: int, db: Session = Depends(get_db)):
    team = db.query(FantaTeam).filter(FantaTeam.id == team_id).first()
    if not team:
        raise HTTPException(404, "Team not found")

    if team.lineage_id is None:
        teams = [team]
    else:
        teams = (
            db.query(FantaTeam)
            .filter(FantaTeam.lineage_id == team.lineage_id)
            .all()
        )
    teams.sort(key=lambda t: t.season.year_start)
    return [
        {"team_id": t.id, "season_id": t.season_id, "season_label": t.season.label, "name": t.name}
        for t in teams
    ]


class LineageLinkRequest(BaseModel):
    team_a_id: int
    team_b_id: int
    keep_distinct_names: bool = True


@teams_router.post("/link-lineage")
def link_team_lineage(
    data: LineageLinkRequest, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
):
    team_a = db.query(FantaTeam).filter(FantaTeam.id == data.team_a_id).first()
    team_b = db.query(FantaTeam).filter(FantaTeam.id == data.team_b_id).first()
    if not team_a or not team_b:
        raise HTTPException(404, "Squadra non trovata")
    if team_a.season_id == team_b.season_id:
        raise HTTPException(
            400,
            "Le due squadre sono della stessa stagione: usa /team-merge/merge per i doppioni, "
            "non il collegamento storico tra stagioni diverse",
        )

    existing_lineage_ids = {t.lineage_id for t in (team_a, team_b) if t.lineage_id is not None}
    if not existing_lineage_ids:
        lineage = FantaTeamLineage()
        db.add(lineage)
        db.flush()
    elif len(existing_lineage_ids) == 1:
        lineage = db.query(FantaTeamLineage).filter(
            FantaTeamLineage.id == next(iter(existing_lineage_ids))
        ).first()
    else:
        # Entrambe avevano gia' una lineage propria (con altre stagioni
        # collegate): le si unifica in una sola, spostando tutte le squadre
        # dalla lineage "persa" a quella "vincente" e cancellando la vuota.
        winner_id, loser_id = sorted(existing_lineage_ids)
        db.query(FantaTeam).filter(FantaTeam.lineage_id == loser_id).update(
            {FantaTeam.lineage_id: winner_id}
        )
        db.query(FantaTeamLineage).filter(FantaTeamLineage.id == loser_id).delete()
        db.flush()
        lineage = db.query(FantaTeamLineage).filter(FantaTeamLineage.id == winner_id).first()

    team_a.lineage_id = lineage.id
    team_b.lineage_id = lineage.id

    if not data.keep_distinct_names:
        older, newer = sorted((team_a, team_b), key=lambda t: t.season.year_start)
        older.name = newer.name

    db.commit()
    return {"ok": True, "lineage_id": lineage.id}


@teams_router.delete("/{team_id}/lineage")
def unlink_team_lineage(team_id: int, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    team = db.query(FantaTeam).filter(FantaTeam.id == team_id).first()
    if not team:
        raise HTTPException(404, "Team not found")
    if team.lineage_id is None:
        raise HTTPException(400, "Questa squadra non ha nessun collegamento storico da rimuovere")

    lineage_id = team.lineage_id
    team.lineage_id = None
    db.flush()

    remaining = db.query(FantaTeam).filter(FantaTeam.lineage_id == lineage_id).count()
    if remaining == 0:
        db.query(FantaTeamLineage).filter(FantaTeamLineage.id == lineage_id).delete()

    db.commit()
    return {"ok": True}


@teams_router.post("/{team_id}/coaches", status_code=201)
def assign_coach(team_id: int, data: CoachAssign, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
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
def remove_coach(team_id: int, allenatore_id: int, db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
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
        "season_label": t.season.label,
        "league_id": t.league_id, "lineage_id": t.lineage_id,
        "credits_spent": t.credits_spent,
        "remaining_credits": t.remaining_credits, "logo_url": logo,
        "coaches": coaches,
    }


router.include_router(allenatori_router)
router.include_router(teams_router)
