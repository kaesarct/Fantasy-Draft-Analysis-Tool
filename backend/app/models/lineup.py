"""Lineup models: LineupSubmission + LineupPlayer."""
import enum
from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

# Panchina standard: P-P-A-A-A-C-C-C-D-D-D
BENCH_ORDER = ["P", "P", "A", "A", "A", "C", "C", "C", "D", "D", "D"]


class LineupSubmission(Base):
    """Formazione schierata per una giornata in una competizione."""
    __tablename__ = "lineup_submissions"

    id = Column(Integer, primary_key=True, index=True)
    fanta_team_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    match_day = Column(Integer, nullable=False)
    module = Column(Integer, nullable=True)          # es. 433, 442, 352...
    submitted_at = Column(DateTime, nullable=True)
    is_default = Column(Boolean, default=False)      # True = formazione recuperata da precedente
    total_score = Column(Integer, nullable=True)     # Punteggio totale calcolato

    __table_args__ = (
        UniqueConstraint(
            "fanta_team_id", "competition_id", "match_day", name="uq_lineup"
        ),
    )

    fanta_team = relationship("FantaTeam", back_populates="lineups")
    competition = relationship("Competition", back_populates="lineups")
    players = relationship("LineupPlayer", back_populates="lineup")


class LineupPlayer(Base):
    """Singolo giocatore in una formazione."""
    __tablename__ = "lineup_players"

    id = Column(Integer, primary_key=True, index=True)
    lineup_id = Column(Integer, ForeignKey("lineup_submissions.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    is_starter = Column(Boolean, default=True)
    bench_order = Column(Integer, nullable=True)   # Posizione in panchina (0-10)
    played = Column(Boolean, nullable=True)         # Ha giocato?
    score = Column(Integer, nullable=True)          # Punteggio di questo giocatore in questa lineup
    got_official_sub = Column(Boolean, default=False)  # Sostituzione d'ufficio (4)

    lineup = relationship("LineupSubmission", back_populates="players")
    player = relationship("Player")
