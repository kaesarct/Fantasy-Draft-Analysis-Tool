"""Auction models — aste per lega."""
import enum
from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, Enum, Date, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class AuctionStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class Auction(Base):
    __tablename__ = "auctions"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    league_id = Column(Integer, ForeignKey("leagues.id"), nullable=False)
    auction_date = Column(Date, nullable=True)
    status = Column(Enum(AuctionStatus), default=AuctionStatus.SCHEDULED)
    # Asta di riparazione (febbraio) vs asta principale
    is_repair = Column(Integer, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    season = relationship("Season", back_populates="auctions")
    bids = relationship("AuctionBid", back_populates="auction")


class AuctionBid(Base):
    """Aggiudicazione di un giocatore all'asta."""
    __tablename__ = "auction_bids"

    id = Column(Integer, primary_key=True, index=True)
    auction_id = Column(Integer, ForeignKey("auctions.id"), nullable=False)
    fanta_team_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    final_price = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("auction_id", "player_id", name="uq_bid_player"),
    )

    auction = relationship("Auction", back_populates="bids")
    fanta_team = relationship("FantaTeam")
    player = relationship("Player")
