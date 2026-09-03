"""Collegamento annuale squadre/allenatori tra leghe.fantacalcio.it e il DB locale.

Sincronizzazione manuale, da fare una volta a inizio stagione (vedi
frontend/.../admin-leghe-sync): non tocca risultati/voti, solo l'identita'
squadra/allenatore — prerequisito per future sync automatiche."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.season import Season
from app.models.fanta_team import FantaTeam, FantaTeamCoach, FantaTeamLineage, League
from app.models.fanta_allenatore import FantaAllenatore
from app.services.auth_service import require_admin
from app.services.leghe_client import LegheClient
from app.services.leghe_competition_sync import apply_competition_list
from app.services.leghe_results_sync import sync_results
from app.services.leghe_lineup_scores_sync import sync_matchday_scores
from app.routers.league import MAIN_LEAGUE_TYPES, _ensure_league_and_competition

router = APIRouter(prefix="/leghe-sync", tags=["leghe-sync"])


def _normalize(name: str) -> str:
    return "".join(c if c.isalnum() else "" for c in name.strip().lower())


@router.get("/participants")
def get_leghe_participants(
    season_id: int, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(404, "Stagione non trovata")

    client = LegheClient()
    client.login()

    # Mappa teamId leghe -> livello campionato (Gold/Bronze/Carbon): le
    # competizioni principali portano gia' l'elenco squadre in "tmids",
    # nessuna chiamata aggiuntiva necessaria. Coppe/Silver condividono lo
    # stesso roster quindi non servono per determinare il campionato.
    leghe_competitions = client.list_competitions()
    team_level: dict[int, str] = {}
    for comp in leghe_competitions:
        level = comp.get("name", "").strip().upper()
        if level not in MAIN_LEAGUE_TYPES:
            continue
        for team_id in comp.get("tmids") or []:
            team_level[team_id] = level

    # Aggancia anche gli id leghe.fantacalcio.it delle Competition gia'
    # esistenti da noi (es. UEFA, creata su leghe solo a fine gironi Ciempions
    # e quindi spesso ancora assente qui): stessa chiamata gia' fatta sopra,
    # nessun costo aggiuntivo.
    competitions_linked = apply_competition_list(db, season, leghe_competitions)

    participants = client.get_participants()

    our_teams = db.query(FantaTeam).filter(FantaTeam.season_id == season_id).all()
    our_teams_by_leghe_id = {t.leghe_team_id: t for t in our_teams if t.leghe_team_id}
    our_teams_by_name = {_normalize(t.name): t for t in our_teams}
    our_allenatori = db.query(FantaAllenatore).order_by(FantaAllenatore.display_name).all()
    our_allenatori_by_email = {a.email.lower(): a for a in our_allenatori if a.email}

    # Squadre di stagioni passate: per una stagione appena creata (senza
    # ancora nessuna FantaTeam propria, es. conclude_season mai lanciato) e'
    # qui che si trova "la squadra storica" a cui agganciare il lineage della
    # nuova riga — la ricerca per nome nella sola stagione corrente sopra
    # sarebbe sempre vuota in quel caso.
    historical_rows = (
        db.query(FantaTeam, Season.label, Season.year_start)
        .join(Season, Season.id == FantaTeam.season_id)
        .filter(FantaTeam.season_id != season_id)
        .order_by(Season.year_start.desc(), FantaTeam.name)
        .all()
    )
    historical_by_name: dict[str, FantaTeam] = {}
    for t, _label, _year in historical_rows:
        historical_by_name.setdefault(_normalize(t.name), t)  # prima occorrenza = stagione piu' recente

    result = []
    for p in participants:
        leghe_team_id = p["teamId"]
        already_linked = our_teams_by_leghe_id.get(leghe_team_id)
        suggested_team = already_linked or our_teams_by_name.get(_normalize(p["teamName"]))
        suggested_lineage_team = None if suggested_team else historical_by_name.get(_normalize(p["teamName"]))

        coaches = []
        for c in p.get("coaches") or []:
            email = (c.get("email") or "").strip().lower()
            matched = our_allenatori_by_email.get(email)
            coaches.append({
                "leghe_coach_id": c["id"],
                "name": (c.get("name") or "").strip(),
                "email": (c.get("email") or "").strip(),
                "suggested_allenatore_id": matched.id if matched else None,
            })

        result.append({
            "leghe_team_id": leghe_team_id,
            "leghe_team_name": p["teamName"].strip(),
            "league_level": team_level.get(leghe_team_id),
            "already_linked_team_id": already_linked.id if already_linked else None,
            "suggested_fanta_team_id": suggested_team.id if suggested_team else None,
            "suggested_lineage_team_id": suggested_lineage_team.id if suggested_lineage_team else None,
            "coaches": coaches,
        })

    return {
        "season_label": season.label,
        "our_teams": [
            {"id": t.id, "name": t.name, "leghe_team_id": t.leghe_team_id} for t in our_teams
        ],
        "historical_teams": [
            {"id": t.id, "name": t.name, "season_label": label}
            for t, label, _year in historical_rows
        ],
        "our_allenatori": [
            {"id": a.id, "display_name": a.display_name, "email": a.email} for a in our_allenatori
        ],
        "participants": result,
        "competitions_linked": competitions_linked,
    }


class CoachDecision(BaseModel):
    leghe_coach_id: int
    allenatore_id: int | None = None
    create: dict | None = None  # {username, display_name, email}
    leghe_email: str | None = None  # email leghe.fantacalcio.it, per aggiornare l'allenatore collegato
    is_primary: bool = False


class TeamDecision(BaseModel):
    leghe_team_id: int
    leghe_team_name: str
    league_level: str | None = None
    fanta_team_id: int | None = None
    create_new: bool = False
    lineage_source_team_id: int | None = None  # squadra storica da cui ereditare il lineage
    new_name: str | None = None
    update_name: bool = False
    coaches: list[CoachDecision] = []


class ApplyRequest(BaseModel):
    season_id: int
    teams: list[TeamDecision]


@router.post("/apply")
def apply_leghe_sync(
    data: ApplyRequest, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
):
    season = db.query(Season).filter(Season.id == data.season_id).first()
    if not season:
        raise HTTPException(404, "Stagione non trovata")

    report = {
        "teams_linked": 0, "teams_created": 0, "teams_renamed": 0,
        "allenatori_created": 0, "allenatori_email_aggiornati": 0, "coaches_assigned": 0,
        "errors": [],
    }

    for team_decision in data.teams:
        savepoint = db.begin_nested()
        try:
            if team_decision.create_new:
                if not team_decision.league_level:
                    raise ValueError(
                        f"{team_decision.leghe_team_name}: campionato mancante, non posso creare la squadra"
                    )
                # Crea lega + competizione se mancano ancora (caso normale a
                # inizio stagione, prima che l'admin le crei a mano altrove):
                # stessa logica gia' usata da POST /competitions e da
                # conclude_season, cosi' non serve un passaggio manuale extra
                # prima di poter creare la prima squadra dell'anno.
                _ensure_league_and_competition(db, season, team_decision.league_level)
                league = db.query(League).filter(
                    League.season_id == season.id, League.level == team_decision.league_level
                ).first()
                team = FantaTeam(
                    name=team_decision.leghe_team_name, season_id=season.id, league_id=league.id
                )
                if team_decision.lineage_source_team_id:
                    source = db.query(FantaTeam).filter(
                        FantaTeam.id == team_decision.lineage_source_team_id
                    ).first()
                    if not source:
                        raise ValueError(
                            f"{team_decision.leghe_team_name}: squadra storica selezionata non trovata"
                        )
                    if not source.lineage_id:
                        lineage = FantaTeamLineage()
                        db.add(lineage)
                        db.flush()
                        source.lineage_id = lineage.id
                    team.lineage_id = source.lineage_id
                db.add(team)
                db.flush()
                report["teams_created"] += 1
            else:
                if not team_decision.fanta_team_id:
                    raise ValueError(f"{team_decision.leghe_team_name}: nessuna squadra selezionata")
                team = db.query(FantaTeam).filter(
                    FantaTeam.id == team_decision.fanta_team_id,
                    FantaTeam.season_id == season.id,
                ).first()
                if not team:
                    raise ValueError(
                        f"{team_decision.leghe_team_name}: squadra selezionata non trovata per questa stagione"
                    )

            if team.leghe_team_id and team.leghe_team_id != team_decision.leghe_team_id:
                raise ValueError(f"{team.name}: già collegata a un'altra squadra leghe.fantacalcio.it")
            team.leghe_team_id = team_decision.leghe_team_id
            report["teams_linked"] += 1

            # Rinomina solo su un match esplicito: una squadra appena creata ha
            # già il nome leghe, e senza update_name confermato dall'admin non
            # tocco un nome storico solo perché diverso da quello su leghe.it.
            if not team_decision.create_new and team_decision.update_name and team_decision.new_name:
                new_name = team_decision.new_name.strip()
                if new_name and new_name != team.name:
                    team.name = new_name
                    report["teams_renamed"] += 1

            for coach_decision in team_decision.coaches:
                if coach_decision.allenatore_id:
                    allenatore = db.query(FantaAllenatore).filter(
                        FantaAllenatore.id == coach_decision.allenatore_id
                    ).first()
                    if not allenatore:
                        raise ValueError(f"{team.name}: allenatore selezionato non trovato")
                    leghe_email = (coach_decision.leghe_email or "").strip() or None
                    if leghe_email and allenatore.email != leghe_email:
                        allenatore.email = leghe_email
                        report["allenatori_email_aggiornati"] += 1
                elif coach_decision.create:
                    c = coach_decision.create
                    username = (c.get("username") or "").strip()
                    display_name = (c.get("display_name") or "").strip()
                    if not username or not display_name:
                        raise ValueError(f"{team.name}: dati allenatore incompleti (username/nome)")
                    if db.query(FantaAllenatore).filter(FantaAllenatore.username.ilike(username)).first():
                        raise ValueError(f"{team.name}: username allenatore '{username}' già esistente")
                    allenatore = FantaAllenatore(
                        username=username, display_name=display_name,
                        email=(c.get("email") or "").strip() or None,
                    )
                    db.add(allenatore)
                    db.flush()
                    report["allenatori_created"] += 1
                else:
                    continue  # nessuna decisione per questo allenatore: lo salto

                if coach_decision.is_primary:
                    # Un solo allenatore primario per squadra (stessa regola di
                    # assign_coach in teams.py).
                    db.query(FantaTeamCoach).filter(
                        FantaTeamCoach.fanta_team_id == team.id,
                        FantaTeamCoach.is_primary == True,
                    ).update({FantaTeamCoach.is_primary: False})

                existing_link = db.query(FantaTeamCoach).filter(
                    FantaTeamCoach.fanta_team_id == team.id,
                    FantaTeamCoach.allenatore_id == allenatore.id,
                ).first()
                if existing_link:
                    existing_link.is_primary = coach_decision.is_primary
                else:
                    db.add(FantaTeamCoach(
                        fanta_team_id=team.id, allenatore_id=allenatore.id,
                        is_primary=coach_decision.is_primary,
                    ))
                    report["coaches_assigned"] += 1

            savepoint.commit()
        except ValueError as e:
            savepoint.rollback()
            report["errors"].append(str(e))

    db.commit()
    return report


@router.post("/sync-results")
def sync_leghe_results(
    season_id: int, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(404, "Stagione non trovata")
    return sync_results(db, season)


@router.post("/sync-matchday-scores")
def sync_leghe_matchday_scores(
    season_id: int, db: Session = Depends(get_db), _admin: str = Depends(require_admin)
):
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(404, "Stagione non trovata")
    return sync_matchday_scores(db, season)
