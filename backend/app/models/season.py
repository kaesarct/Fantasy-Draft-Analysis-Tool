"""Season model."""
from sqlalchemy import Column, Integer, String, Date, Boolean
from sqlalchemy.orm import relationship
from app.database import Base


class Season(Base):
    __tablename__ = "seasons"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(10), unique=True, nullable=False)  # e.g. "2024-25"
    year_start = Column(Integer, nullable=False)               # 2024
    year_end = Column(Integer, nullable=False)                 # 2025
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_current = Column(Boolean, default=False)

    leagues = relationship("League", back_populates="season")
    fanta_teams = relationship("FantaTeam", back_populates="season")
    competitions = relationship("Competition", back_populates="season")
    player_snapshots = relationship("PlayerSnapshot", back_populates="season")
    auctions = relationship("Auction", back_populates="season")
