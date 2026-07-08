"""Trade model — scambi tra squadre della stessa lega."""
from sqlalchemy import Column, Integer, Float, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    team_a_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    team_b_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    approved_at = Column(DateTime, nullable=True)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("TradeItem", back_populates="trade")


class TradeItem(Base):
    """Singolo giocatore coinvolto in uno scambio."""
    __tablename__ = "trade_items"

    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    from_team_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    to_team_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    # Prezzi prima e dopo la trasposizione (secondo la regola scambi)
    price_before = Column(Float, nullable=True)
    price_after = Column(Float, nullable=True)

    trade = relationship("Trade", back_populates="items")
    player = relationship("Player")
