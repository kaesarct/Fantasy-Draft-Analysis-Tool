"""Giocatori presenti nelle quotazioni storiche ma senza riga in `players`."""
from sqlalchemy.orm import Session

from app.models.player import Player
from app.models.season_data import PlayerSeasonPrice


def create_missing_players_from_prices(db: Session) -> int:
    """L'elenco Giocatori di una stagione passata parte dalla tabella `players`: chi ha
    quotazioni storiche ma non e' mai stato creato (non e' nella lista del sync live
    attuale e non e' mai stato in una rosa importata) non comparirebbe mai. Crea la
    riga mancante, per fanta_id, con nome e ruolo della stagione piu' recente in cui
    compare. Non fa commit. Idempotente."""
    existing_fanta_ids = {
        row[0] for row in db.query(Player.fanta_id).filter(Player.fanta_id.isnot(None)).all()
    }

    latest_by_fanta_id: dict[int, PlayerSeasonPrice] = {}
    for row in db.query(PlayerSeasonPrice).order_by(PlayerSeasonPrice.season_id):
        if row.fanta_player_id not in existing_fanta_ids and (row.player_name or "").strip():
            latest_by_fanta_id[row.fanta_player_id] = row  # in ordine di stagione: vince la piu' recente

    for fanta_id, row in latest_by_fanta_id.items():
        db.add(Player(
            fanta_id=fanta_id,
            name=row.player_name.strip(),
            role=row.role or "?",
            secondary_role=row.secondary_role,
        ))
    db.flush()
    return len(latest_by_fanta_id)
