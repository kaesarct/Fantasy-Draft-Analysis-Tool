"""Aggiorna Competition.leghe_id incrociando LegheClient.list_competitions().

Aggancia solo le Competition gia' esistenti nel nostro DB (mai le crea): una
competizione come UEFA viene creata su leghe.fantacalcio.it solo a fine gironi
Ciempions, quando ancora non sappiamo chi vi accede — la creiamo noi via
Gestione Squadre quando arriva il momento, e da quel momento questo check la
aggancia automaticamente al suo id leghe. Le competizioni leghe senza
corrispondenza in CompetitionType (es. tornei extra come "Tenkaichi") vengono
ignorate: non tracciate."""
from sqlalchemy.orm import Session

from app.models.competition import Competition, CompetitionType
from app.models.season import Season
from app.services.leghe_client import LegheClient

NAME_MAP = {"COPPA ITALIA": "COPPA_ITALIA", "EURO CUP": "EURO_CUP"}
KNOWN_TYPES = {t.value for t in CompetitionType}


def apply_competition_list(db: Session, season: Season, leghe_competitions: list[dict]) -> list[str]:
    """Aggiorna leghe_id sulle Competition della stagione a partire da una
    risposta di list_competitions() gia' scaricata (evita una seconda chiamata
    quando il chiamante ce l'ha gia')."""
    updated = []
    for comp in leghe_competitions:
        raw_name = (comp.get("name") or "").strip().upper()
        comp_type = NAME_MAP.get(raw_name, raw_name)
        if comp_type not in KNOWN_TYPES:
            continue  # torneo extra non tracciato (es. "Tenkaichi")

        our_comp = db.query(Competition).filter(
            Competition.season_id == season.id, Competition.type == comp_type
        ).first()
        if our_comp and our_comp.leghe_id != comp["id"]:
            our_comp.leghe_id = comp["id"]
            updated.append(comp_type)

    if updated:
        db.commit()
    return updated


def sync_competition_leghe_ids(db: Session, season: Season, client: LegheClient | None = None) -> list[str]:
    client = client or LegheClient()
    client.login()
    return apply_competition_list(db, season, client.list_competitions())
