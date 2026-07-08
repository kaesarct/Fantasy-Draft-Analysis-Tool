"""Injury model."""
from sqlalchemy import Column, Integer, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class InjuryPlayer(Base):
    __tablename__ = "injury_players"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    report_date = Column(Date, nullable=True)           # Data bollettino medico
    expected_weeks = Column(Integer, nullable=True)     # Settimane di stop previste
    expected_return = Column(Date, nullable=True)       # Rientro stimato
    confirmed_return = Column(Date, nullable=True)      # Rientro confermato (convocazione)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)           # False dopo il rientro
    qualifies_for_temp_sub = Column(Boolean, default=False)  # ≥ 8 settimane
    created_at = Column(DateTime, default=datetime.utcnow)

    player = relationship("Player", back_populates="injuries")
