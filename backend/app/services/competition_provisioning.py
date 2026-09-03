"""Crea Competition (e, per Gold/Bronze/Carbon, la League) per una stagione.

Vive in app/services/ e non in app/routers/league.py apposta: e' usata anche
da servizi di sync (leghe_competition_sync.py, chiamato da sync_service.py)
che a loro volta sono importati da router diversi da league.py — tenerla in
un router avrebbe creato un import circolare (league.py -> injuries.py ->
sync_service.py -> di nuovo league.py)."""
from sqlalchemy.orm import Session

from app.models.competition import Competition
from app.models.fanta_team import League
from app.models.season import Season

# Gold/Bronze/Carbon hanno l'iscrizione automatica tramite FantaTeam.league_id
# (stessa distinzione usata in frontend/.../admin-teams.component.ts).
MAIN_LEAGUE_TYPES = {"GOLD", "BRONZE", "CARBON"}


def _ensure_league_and_competition(db: Session, season: Season, comp_type: str, name: str | None = None) -> Competition:
    """Crea la Competition (e, per Gold/Bronze/Carbon, la League se manca)
    per una stagione. Non fa il commit: chi chiama decide la transazione."""
    existing = db.query(Competition).filter(
        Competition.season_id == season.id, Competition.type == comp_type
    ).first()
    if existing:
        return existing

    # Gold/Bronze/Carbon hanno iscrizione automatica via League: se manca la
    # lega di quel livello per la stagione, la creo insieme alla competizione
    # (altrimenti la competizione risulterebbe senza nessuna squadra eleggibile).
    if comp_type in MAIN_LEAGUE_TYPES:
        league = db.query(League).filter(
            League.season_id == season.id, League.level == comp_type
        ).first()
        if not league:
            league = League(season_id=season.id, level=comp_type)
            db.add(league)
            db.flush()

    comp = Competition(
        season_id=season.id, type=comp_type,
        name=name or f"{comp_type.capitalize()} {season.label}",
    )
    db.add(comp)
    db.flush()
    return comp
