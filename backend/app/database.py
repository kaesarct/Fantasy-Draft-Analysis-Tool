from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings
import os

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
        lineup,
        lineup_import,
        season_data,
        trade,
        auction,
    )
    Base.metadata.create_all(bind=engine)
    _migrate_add_leghe_id()


def _migrate_add_leghe_id():
    # create_all non altera tabelle esistenti: la colonna va aggiunta a mano
    # sui DB gia' creati (idempotente grazie a IF NOT EXISTS).
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE competitions ADD COLUMN IF NOT EXISTS leghe_id INTEGER"
        ))
