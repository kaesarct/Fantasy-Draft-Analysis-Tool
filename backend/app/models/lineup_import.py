"""LineupRawImport: JSON grezzo delle formazioni scaricate da leghe.fantacalcio.it."""
from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from datetime import datetime
from app.database import Base


class LineupRawImport(Base):
    """Payload grezzo per (competizione leghe, giornata) — conservato per audit e
    riprocessamento: la struttura del JSON non e' consolidata."""
    __tablename__ = "lineup_raw_imports"

    id = Column(Integer, primary_key=True, index=True)
    leghe_competition_id = Column(Integer, nullable=False)
    competition_name = Column(String(100), nullable=False)
    match_day = Column(Integer, nullable=False, default=0)  # 0 = giornata sconosciuta
    raw_json = Column(Text, nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("leghe_competition_id", "match_day", name="uq_lineup_raw"),
    )
