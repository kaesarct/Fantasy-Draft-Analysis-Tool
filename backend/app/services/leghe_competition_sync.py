"""Crea/aggancia le Competition della stagione a partire da list_competitions().

Ogni competizione trovata su leghe.fantacalcio.it (tra quelle note — vedi
KNOWN_TYPES) viene creata automaticamente se manca ancora da noi (con la
relativa League, per Gold/Bronze/Carbon), riusando la stessa logica gia'
in POST /competitions e conclude_season. Chiamato sia dal caricamento
squadre/allenatori sia da ogni sync di routine (voti, quotazioni, punteggi,
risultati): cosi' una competizione come UEFA, che leghe.fantacalcio.it crea
solo a fine gironi Ciempions, viene recepita in automatico al primo sync
utile, senza un passaggio manuale da Gestione Squadre. Le competizioni leghe
senza corrispondenza in CompetitionType (es. tornei extra come "Tenkaichi")
restano ignorate: non tracciate."""
from sqlalchemy.orm import Session

from app.models.competition import Competition, CompetitionType
from app.models.season import Season
from app.services.competition_provisioning import _ensure_league_and_competition
from app.services.leghe_client import LegheClient

NAME_MAP = {"COPPA ITALIA": "COPPA_ITALIA", "EURO CUP": "EURO_CUP"}
KNOWN_TYPES = {t.value for t in CompetitionType}


def ensure_competitions(db: Session, season: Season, leghe_competitions: list[dict]) -> dict:
    """Crea (se mancano) e aggancia leghe_id per ogni competizione nota
    trovata su leghe.fantacalcio.it, a partire da una risposta di
    list_competitions() gia' scaricata (evita una seconda chiamata quando il
    chiamante ce l'ha gia'). Ritorna {created: [...], linked: [...]}."""
    created = []
    linked = []
    for comp in leghe_competitions:
        raw_name = (comp.get("name") or "").strip().upper()
        comp_type = NAME_MAP.get(raw_name, raw_name)
        if comp_type not in KNOWN_TYPES:
            continue  # torneo extra non tracciato (es. "Tenkaichi")

        existing = db.query(Competition).filter(
            Competition.season_id == season.id, Competition.type == comp_type
        ).first()
        if not existing:
            _ensure_league_and_competition(db, season, comp_type)
            existing = db.query(Competition).filter(
                Competition.season_id == season.id, Competition.type == comp_type
            ).first()
            created.append(comp_type)

        if existing.leghe_id != comp["id"]:
            existing.leghe_id = comp["id"]
            linked.append(comp_type)

    if created or linked:
        db.commit()
    return {"created": created, "linked": linked}


def sync_competition_leghe_ids(db: Session, season: Season, client: LegheClient | None = None) -> dict:
    client = client or LegheClient()
    client.login()
    return ensure_competitions(db, season, client.list_competitions())
