"""Tracking storico infortunati Serie A, da fantacalcio.it/infortunati-serie-a."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class SerieAInjuryReport(Base):
    """Infortunio attivo (il giocatore e' attualmente sulla pagina)."""
    __tablename__ = "serie_a_injury_reports"

    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String(100), nullable=False)   # come scrapato, es. "Idrissi R."
    team_name = Column(String(100), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)  # match best-effort
    description = Column(Text, nullable=False)
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    last_updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("player_name", "team_name", name="uq_seriea_injury_report"),)

    player = relationship("Player")
    descriptions = relationship(
        "SerieAInjuryDescription", back_populates="report", cascade="all, delete-orphan"
    )


class SerieAInjuryArchive(Base):
    """Infortunio concluso (il giocatore non e' piu' sulla pagina = rientrato)."""
    __tablename__ = "serie_a_injury_archives"

    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String(100), nullable=False)
    team_name = Column(String(100), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    last_description = Column(Text, nullable=False)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=False)

    player = relationship("Player")
    descriptions = relationship("SerieAInjuryDescription", back_populates="archive")


class SerieAInjuryDescription(Base):
    """Storico delle descrizioni: sopravvive al passaggio report -> archive."""
    __tablename__ = "serie_a_injury_descriptions"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("serie_a_injury_reports.id"), nullable=True)
    archive_id = Column(Integer, ForeignKey("serie_a_injury_archives.id"), nullable=True)
    description = Column(Text, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    report = relationship("SerieAInjuryReport", back_populates="descriptions")
    archive = relationship("SerieAInjuryArchive", back_populates="descriptions")
