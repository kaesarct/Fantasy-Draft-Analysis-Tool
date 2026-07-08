"""SerieA Team model."""
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class SerieATeam(Base):
    __tablename__ = "serie_a_teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    abbreviation = Column(String(5), unique=True, nullable=False)
    fanta_id = Column(Integer, nullable=True)  # ID sul sito fantacalcio.it

    players = relationship("Player", back_populates="serie_a_team")
