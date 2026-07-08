"""Player models: Player (registry) + PlayerSnapshot (per-matchday stats) + PlayerMatchScore."""
from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    fanta_id = Column(Integer, unique=True, nullable=True)   # ID su fantacalcio.it
    name = Column(String(150), nullable=False, index=True)
    role = Column(String(2), nullable=False)                 # P, D, C, A
    secondary_role = Column(String(2), nullable=True)
    serie_a_team_id = Column(Integer, ForeignKey("serie_a_teams.id"), nullable=True)

    serie_a_team = relationship("SerieATeam", back_populates="players")
    snapshots = relationship("PlayerSnapshot", back_populates="player")
    scores = relationship("PlayerMatchScore", back_populates="player")
    fanta_rosters = relationship("FantaRoster", back_populates="player")
    injuries = relationship("InjuryPlayer", back_populates="player")


class PlayerSnapshot(Base):
    """Storico quotazioni per giornata."""
    __tablename__ = "player_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    match_day = Column(Integer, nullable=False)
    price = Column(Float, default=0.0)         # Qt.A (prezzo attuale)
    price_initial = Column(Float, default=0.0) # Qt.I (prezzo iniziale stagione)
    price_diff = Column(Float, default=0.0)    # Diff.
    price_mantra = Column(Float, default=0.0)  # Qt.A M
    price_mantra_initial = Column(Float, default=0.0)  # Qt.I M
    price_mantra_diff = Column(Float, default=0.0)     # Diff.M
    fvm = Column(Float, default=0.0)           # FVM classico
    fvm_mantra = Column(Float, default=0.0)    # FVM Mantra

    __table_args__ = (
        UniqueConstraint("player_id", "season_id", "match_day", name="uq_snapshot"),
    )

    player = relationship("Player", back_populates="snapshots")
    season = relationship("Season", back_populates="player_snapshots")


class PlayerMatchScore(Base):
    """Voto e bonus/malus di un giocatore per una giornata."""
    __tablename__ = "player_match_scores"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    match_day = Column(Integer, nullable=False)
    vote = Column(Float, nullable=True)        # Voto base (pagella)
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)
    own_goals = Column(Integer, default=0)
    penalties_saved = Column(Integer, default=0)
    penalties_missed = Column(Integer, default=0)
    clean_sheet_bonus = Column(Float, default=0.0)
    bonus_total = Column(Float, default=0.0)
    malus_total = Column(Float, default=0.0)
    total_score = Column(Float, nullable=True)  # Voto finale con bonus/malus

    __table_args__ = (
        UniqueConstraint("player_id", "season_id", "match_day", name="uq_score"),
    )

    player = relationship("Player", back_populates="scores")
