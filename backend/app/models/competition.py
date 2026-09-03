"""Competition models: Competition, Group, GroupTeam, MatchResult, CompetitionStanding."""
import enum
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    ForeignKey, Enum, UniqueConstraint, DateTime,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class CompetitionType(str, enum.Enum):
    GOLD = "GOLD"
    BRONZE = "BRONZE"
    CARBON = "CARBON"
    SILVER = "SILVER"
    CIEMPIONS = "CIEMPIONS"
    UEFA = "UEFA"
    COPPA_ITALIA = "COPPA_ITALIA"
    EURO_CUP = "EURO_CUP"


class CompetitionPhase(str, enum.Enum):
    GROUP = "GROUP"
    ROUND_OF_16 = "ROUND_OF_16"
    QUARTER_FINAL = "QUARTER_FINAL"
    SEMI_FINAL = "SEMI_FINAL"
    FINAL = "FINAL"
    REGULAR = "REGULAR"  # Per i campionati a girone unico


class Competition(Base):
    __tablename__ = "competitions"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    type = Column(Enum(CompetitionType), nullable=False)
    name = Column(String(100), nullable=False)   # "Gold League 2024-25"
    is_active = Column(Boolean, default=True)
    leghe_id = Column(Integer, nullable=True)    # id competizione su leghe.fantacalcio.it

    season = relationship("Season", back_populates="competitions")
    groups = relationship("CompetitionGroup", back_populates="competition")
    match_results = relationship("MatchResult", back_populates="competition")
    standings = relationship("CompetitionStanding", back_populates="competition")
    lineups = relationship("LineupSubmission", back_populates="competition")


class CompetitionGroup(Base):
    """Gironi per Ciempions/UEFA."""
    __tablename__ = "competition_groups"

    id = Column(Integer, primary_key=True, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    name = Column(String(20), nullable=False)  # "Girone A"

    competition = relationship("Competition", back_populates="groups")
    group_teams = relationship("CompetitionGroupTeam", back_populates="group")


class CompetitionGroupTeam(Base):
    """Squadre in un girone."""
    __tablename__ = "competition_group_teams"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("competition_groups.id"), nullable=False)
    fanta_team_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("group_id", "fanta_team_id", name="uq_group_team"),
    )

    group = relationship("CompetitionGroup", back_populates="group_teams")


class MatchResult(Base):
    """Risultato di una partita tra due fanta-team."""
    __tablename__ = "match_results"

    id = Column(Integer, primary_key=True, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    fanta_team_home_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    fanta_team_away_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    match_day = Column(Integer, nullable=False)
    phase = Column(Enum(CompetitionPhase), default=CompetitionPhase.REGULAR)
    # Punteggi totalizzati (somma voti+bonus di tutti i giocatori schierati)
    score_home = Column(Float, nullable=True)
    score_away = Column(Float, nullable=True)
    # Gol fantacalcio calcolati dalle fasce
    goals_home = Column(Integer, default=0)
    goals_away = Column(Integer, default=0)
    # Punti classifica assegnati (3=vittoria, 1=pareggio, 0=sconfitta)
    pts_home = Column(Integer, default=0)
    pts_away = Column(Integer, default=0)
    # Premio Oscar/Goku
    is_oscar = Column(Boolean, default=False)   # punteggio più basso stagione
    is_goku = Column(Boolean, default=False)    # punteggio più alto stagione
    played_at = Column(DateTime, nullable=True)

    competition = relationship("Competition", back_populates="match_results")
    home_team = relationship(
        "FantaTeam", foreign_keys=[fanta_team_home_id], back_populates="home_matches"
    )
    away_team = relationship(
        "FantaTeam", foreign_keys=[fanta_team_away_id], back_populates="away_matches"
    )


class CompetitionStanding(Base):
    """Snapshot classifica per competizione, squadra e giornata (storico)."""
    __tablename__ = "competition_standings"

    id = Column(Integer, primary_key=True, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    fanta_team_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    match_day = Column(Integer, nullable=False)
    # Campionato diretto
    played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    goals_for = Column(Float, default=0.0)      # Punteggio fatto
    goals_against = Column(Float, default=0.0)  # Punteggio subito
    pts = Column(Integer, default=0)
    # Classifica Silver (accumulo)
    total_score = Column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint(
            "competition_id", "fanta_team_id", "match_day", name="uq_standing"
        ),
    )

    competition = relationship("Competition", back_populates="standings")
    fanta_team = relationship("FantaTeam", back_populates="standings")


class CompetitionMatchdayScore(Base):
    """Punteggio di una squadra in una singola giornata, senza bisogno di un
    avversario (a differenza di MatchResult) — sincronizzato da leghe.fantacalcio.it
    via GET gaming/v1/teamLineup (campo "tot"), l'unica fonte che funziona anche
    per competizioni senza scontri diretti come Silver."""
    __tablename__ = "competition_matchday_scores"

    id = Column(Integer, primary_key=True, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)
    fanta_team_id = Column(Integer, ForeignKey("fanta_teams.id"), nullable=False)
    match_day = Column(Integer, nullable=False)
    score = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "competition_id", "fanta_team_id", "match_day", name="uq_matchday_score"
        ),
    )


class AwardType(str, enum.Enum):
    GOKU = "GOKU"     # punteggio più alto della stagione
    OSCAR = "OSCAR"   # punteggio più basso della stagione


class SeasonAward(Base):
    """Premio Goku/Oscar (punteggio più alto/basso di giornata) per stagione.
    Storico immutabile inserito una tantum (vedi database.py::_migrate_seed_season_awards);
    la stagione corrente viene invece calcolata a runtime, non salvata qui."""
    __tablename__ = "season_awards"

    id = Column(Integer, primary_key=True, index=True)
    season_label = Column(String(10), nullable=False)   # es. "2019-20"
    award_type = Column(Enum(AwardType), nullable=False)
    team_name = Column(String(100), nullable=False)
    score = Column(Float, nullable=False)
    detail = Column(String(100), nullable=False)         # es. "17ª giornata" o "semifinale andata Ciempions"

    __table_args__ = (
        UniqueConstraint("season_label", "award_type", name="uq_season_award"),
    )
