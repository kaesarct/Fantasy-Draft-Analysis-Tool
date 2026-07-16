import logging
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    os.makedirs(settings.download_folder, exist_ok=True)
    os.makedirs(settings.upload_folder, exist_ok=True)
    from app.models import (  # noqa: F401 — import all models so Base knows them
        player,
        serie_a_team,
        fanta_allenatore,
        fanta_team,
        season,
        competition,
        injury,
        serie_a_injury,
        lineup,
        lineup_import,
        season_data,
        trade,
        auction,
    )
    Base.metadata.create_all(bind=engine)
    _migrate_add_leghe_id()
    _migrate_widen_secondary_role()
    # L'ordine conta: normalizzare prima uniforma le eventuali coppie duplicate
    # che differiscono solo per maiuscole/minuscole (es. "ALBIOL" vs "Albiol"),
    # cosi' la deduplica le riconosce come lo stesso nome.
    _migrate_normalize_player_names()
    _migrate_dedupe_players()


def _migrate_add_leghe_id():
    # create_all non altera tabelle esistenti: la colonna va aggiunta a mano
    # sui DB gia' creati (idempotente grazie a IF NOT EXISTS).
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE competitions ADD COLUMN IF NOT EXISTS leghe_id INTEGER"
        ))


def _migrate_widen_secondary_role():
    # create_all non altera tabelle esistenti: il campo puo' contenere una lista
    # di ruoli Mantra separata da ";" (es. "B;Dd;E"), va allargata a mano sui DB
    # gia' creati con il VARCHAR(2) originale.
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE players ALTER COLUMN secondary_role TYPE VARCHAR(50)"
        ))


def _migrate_dedupe_players():
    """L'import storico rose (backend/etl/import_history.py) crea Player per
    nome, senza fanta_id: quando il sync live quotazioni crea poi lo stesso
    giocatore per fanta_id, restano due righe distinte per la stessa persona
    (una con fanta_id NULL, una valorizzata). Ricollega lo storico rose
    (l'unico dato reale sulla riga senza fanta_id, verificato non esserci
    altrove) alla riga con fanta_id ed elimina il duplicato. Idempotente:
    se non ci sono piu' duplicati non fa nulla."""
    from sqlalchemy import func
    from app.models.player import Player
    from app.models.fanta_team import FantaRoster

    db = SessionLocal()
    try:
        duplicated_names = [
            row[0] for row in
            db.query(Player.name).group_by(Player.name).having(func.count() > 1).all()
        ]
        if not duplicated_names:
            return

        merged_players = 0
        relinked_rosters = 0
        for name in duplicated_names:
            candidates = db.query(Player).filter(Player.name == name).all()
            without_fanta_id = [p for p in candidates if p.fanta_id is None]
            with_fanta_id = [p for p in candidates if p.fanta_id is not None]
            if len(without_fanta_id) != 1 or len(with_fanta_id) != 1:
                # Non il pattern atteso (1 senza + 1 con fanta_id): non tocco
                # nulla, va risolto a mano.
                continue

            old_player = without_fanta_id[0]
            keep_player = with_fanta_id[0]

            rosters = db.query(FantaRoster).filter(FantaRoster.player_id == old_player.id).all()
            for roster in rosters:
                conflict = db.query(FantaRoster).filter(
                    FantaRoster.player_id == keep_player.id,
                    FantaRoster.fanta_team_id == roster.fanta_team_id,
                    FantaRoster.season_id == roster.season_id,
                ).first()
                if conflict:
                    # Il giocatore risulta gia' in quella rosa sull'altra riga:
                    # non sovrascrivo, lascio la riga vecchia per non perdere dati.
                    continue
                roster.player_id = keep_player.id
                relinked_rosters += 1

            db.flush()
            remaining = db.query(FantaRoster).filter(FantaRoster.player_id == old_player.id).count()
            if remaining == 0:
                db.delete(old_player)
                merged_players += 1

        db.commit()
        if merged_players:
            logger.info(
                "Deduplica giocatori: %s righe duplicate rimosse, %s rose ricollegate",
                merged_players, relinked_rosters,
            )
    finally:
        db.close()


def _migrate_normalize_player_names():
    """Alcuni giocatori (import storico) hanno il nome tutto maiuscolo
    (es. "ACERBI") invece del formato stile fantacalcio.it (es. "Acerbi",
    "De Gea", "N'Dicka"). Uniforma con str.title(), verificato a mano sui
    casi con apostrofi/trattini/nomi doppi. Idempotente."""
    from app.models.player import Player

    db = SessionLocal()
    try:
        normalized = 0
        for p in db.query(Player).all():
            if p.name == p.name.upper() and p.name != p.name.title():
                p.name = p.name.title()
                normalized += 1
        db.commit()
        if normalized:
            logger.info("Normalizzati %s nomi giocatore da MAIUSCOLO a Title Case", normalized)
    finally:
        db.close()
