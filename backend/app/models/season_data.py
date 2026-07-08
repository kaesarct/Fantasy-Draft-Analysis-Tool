"""Import storico per stagione da fantacalcio.it: stats aggregate e quotazioni."""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from datetime import datetime
from app.database import Base


class ImportedSeasonData(Base):
    """Traccia gli import gia' eseguiti per evitare download ripetuti."""
    __tablename__ = "imported_season_data"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    data_type = Column(String(10), nullable=False)  # "stats" | "prices"
    imported_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("season_id", "data_type", name="uq_imported_season"),
    )


class PlayerSeasonStat(Base):
    """Statistiche aggregate di fine stagione per giocatore (Excel stats di fantacalcio.it)."""
    __tablename__ = "player_season_stats"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    fanta_player_id = Column(Integer, nullable=False)
    role = Column(String(2), nullable=True)
    player_name = Column(String(150), nullable=True)
    team = Column(String(50), nullable=True)
    matches_played = Column(Float, nullable=True)
    average_vote = Column(Float, nullable=True)
    fantasy_average = Column(Float, nullable=True)
    goals_scored = Column(Float, nullable=True)
    goals_conceded = Column(Float, nullable=True)
    penalties_saved = Column(Float, nullable=True)
    penalties_scored = Column(Float, nullable=True)
    penalties_missed = Column(Float, nullable=True)
    assists = Column(Float, nullable=True)
    yellow_cards = Column(Float, nullable=True)
    red_cards = Column(Float, nullable=True)
    own_goals = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("season_id", "fanta_player_id", name="uq_season_stat"),
    )


class PlayerSeasonPrice(Base):
    """Quotazioni di stagione per giocatore (Excel prices di fantacalcio.it)."""
    __tablename__ = "player_season_prices"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    fanta_player_id = Column(Integer, nullable=False)
    role = Column(String(2), nullable=True)
    secondary_role = Column(String(10), nullable=True)
    player_name = Column(String(150), nullable=True)
    team = Column(String(50), nullable=True)
    market_value_a = Column(Float, nullable=True)
    market_value_i = Column(Float, nullable=True)
    difference = Column(Float, nullable=True)
    market_value_a_m = Column(Float, nullable=True)
    market_value_i_m = Column(Float, nullable=True)
    difference_m = Column(Float, nullable=True)
    fvm = Column(Float, nullable=True)
    fvm_m = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("season_id", "fanta_player_id", name="uq_season_price"),
    )
