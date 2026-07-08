"""FantaTeam, FantaTeamCoach (M2M), FantaTeamLogo, FantaRoster, FantaRosterTempSub."""
import enum
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    ForeignKey, Enum, UniqueConstraint, DateTime,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class LeagueLevel(str, enum.Enum):
    GOLD = "GOLD"
    BRONZE = "BRONZE"
    CARBON = "CARBON"


class League(Base):
    __tablename__ = "leagues"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    level = Column(Enum(LeagueLevel), nullable=False)  # GOLD, BRONZE, CARBON
    fanta_lega_id = Column(String(100), nullable=True)  # ID/slug su fantacalcio.it

    season = relationship("Season", back_populates="leagues")
    fanta_teams = relationship("FantaTeam", back_populates="league")


class FantaTeam(Base):
    """Una squadra in una specifica stagione."""
    __tablename__ = "fanta_teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    league_id = Column(Integer, ForeignKey("leagues.id"), nullable=False)
    credits_spent = Column(Float, default=0.0)
    remaining_credits = Column(Float, default=350.0)
    # Palmarès come lista JSON serializzata (badge type list)
    badges = Column(String(500), default="[]")

    season = relationship("Season", back_populates="fanta_teams")
    league = relationship("League", back_populates="fanta_teams")
    logos = relationship("FantaTeamLogo", back_populates="fanta_team")
    coaches = relationship("FantaTeamCoach", back_populates="fanta_team")
    rosters = relationship("FantaRoster", back_populates="fanta_team")
    home_matches = relationship(
        "MatchResult", foreign_keys="MatchResult.fanta_team_home_id", back_populates="home_team"
    )
    away_matches = relationship(
        "MatchResult", foreign_keys="MatchResult.fanta_team_away_id", back_populates="away_team"
    )
    standings = relationship("CompetitionStanding", back_populates="fanta_team")
    lineups = relationship("LineupSubmission", back_populates="fanta_team")


class FantaTeamCoach(Base):
    """M2M: più allenatori per squadra."""
    __tablename__ = "fanta_team_coaches"

    id = Column(Integer, primary_key=True, index=True)
    fanta_team_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    allenatore_id = Column(Integer, ForeignKey("fanta_allenatori.id"), nullable=False)
    is_primary = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("fanta_team_id", "allenatore_id", name="uq_team_coach"),
    )

    fanta_team = relationship("FantaTeam", back_populates="coaches")
    allenatore = relationship("FantaAllenatore", back_populates="team_coaches")


class FantaTeamLogo(Base):
    """Logo della squadra per ogni stagione."""
    __tablename__ = "fanta_team_logos"

    id = Column(Integer, primary_key=True, index=True)
    fanta_team_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    logo_url = Column(String(500), nullable=True)   # path relativo o URL

    __table_args__ = (
        UniqueConstraint("fanta_team_id", "season_id", name="uq_team_logo_season"),
    )

    fanta_team = relationship("FantaTeam", back_populates="logos")


class FantaRoster(Base):
    """Rosa di una squadra per stagione (aggiornata ad ogni mercato)."""
    __tablename__ = "fanta_rosters"

    id = Column(Integer, primary_key=True, index=True)
    fanta_team_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    purchase_price = Column(Float, nullable=False)  # Prezzo d'asta
    is_active = Column(Boolean, default=True)        # False se ceduto/scambiato
    acquired_at = Column(DateTime, default=datetime.utcnow)
    released_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("fanta_team_id", "player_id", "season_id", name="uq_roster"),
    )

    fanta_team = relationship("FantaTeam", back_populates="rosters")
    player = relationship("Player", back_populates="fanta_rosters")
    temp_subs = relationship("FantaRosterTempSub", back_populates="roster_entry")


class FantaRosterTempSub(Base):
    """Sostituzione temporanea per infortuni ≥ 8 settimane."""
    __tablename__ = "fanta_roster_temp_subs"

    id = Column(Integer, primary_key=True, index=True)
    roster_entry_id = Column(Integer, ForeignKey("fanta_rosters.id"), nullable=False)
    replacement_player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    start_match_day = Column(Integer, nullable=False)
    end_match_day = Column(Integer, nullable=True)  # Null finché il titolare non rientra
    is_active = Column(Boolean, default=True)

    roster_entry = relationship("FantaRoster", back_populates="temp_subs")
    replacement_player = relationship("Player", foreign_keys=[replacement_player_id])
