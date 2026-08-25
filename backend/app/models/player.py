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
    secondary_role = Column(String(50), nullable=True)  # ruoli Mantra, lista separata da ";" es. "B;Dd;E"
    serie_a_team_id = Column(Integer, ForeignKey("serie_a_teams.id"), nullable=True)

    serie_a_team = relationship("SerieATeam", back_populates="players")
    snapshots = relationship("PlayerSnapshot", back_populates="player")
    scores = relationship("PlayerMatchScore", back_populates="player")
    season_stats = relationship("PlayerArchiveSeasonStat", back_populates="player")
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


class PlayerArchiveSeasonStat(Base):
    """Statistiche aggregate di stagione (fonte: archivio storico esterno,
    usato per le stagioni 2006-07..2014-15 di cui non abbiamo dati per
    giornata). Una riga per player+stagione+squadra (piu' di una se il
    giocatore ha cambiato squadra durante l'anno)."""
    __tablename__ = "player_archive_season_stats"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    team_name = Column(String(100), nullable=True)
    role = Column(String(2), nullable=True)

    presences = Column(Integer, default=0)         # P
    starter_count = Column(Integer, default=0)      # T
    quota = Column(Float, nullable=True)             # Q

    vote_gazzetta = Column(Float, nullable=True)     # MG
    vote_corriere = Column(Float, nullable=True)      # MC
    vote_tuttosport = Column(Float, nullable=True)   # MT
    vote_avg2 = Column(Float, nullable=True)          # M2
    vote_avg3 = Column(Float, nullable=True)          # M3
    vote_fantacalcio = Column(Float, nullable=True)   # MF

    goals_scored = Column(Integer, default=0)        # GF
    goals_conceded = Column(Integer, default=0)      # GS (solo portieri)
    assists = Column(Integer, default=0)              # AS
    own_goals = Column(Integer, default=0)            # AU
    yellow_cards = Column(Integer, default=0)         # A
    red_cards = Column(Integer, default=0)            # E
    penalties_scored = Column(Integer, default=0)    # TR
    penalties_missed = Column(Integer, default=0)     # SB
    penalties_saved = Column(Integer, default=0)      # PA
    penalties_conceded = Column(Integer, default=0)  # SU

    __table_args__ = (
        UniqueConstraint("player_id", "season_id", "team_name", name="uq_player_season_stat"),
    )

    player = relationship("Player", back_populates="season_stats")


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
