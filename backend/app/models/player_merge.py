"""Rifiuti di merge giocatori — coppie simili confermate come persone diverse."""
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint
from app.database import Base


class PlayerMergeDismissal(Base):
    """Coppia di giocatori segnalata come simile ma confermata NON essere la
    stessa persona: esclude la coppia dai futuri ricontrolli."""
    __tablename__ = "player_merge_dismissals"

    id = Column(Integer, primary_key=True, index=True)
    player_id_low = Column(Integer, ForeignKey("players.id"), nullable=False)
    player_id_high = Column(Integer, ForeignKey("players.id"), nullable=False)
    dismissed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("player_id_low", "player_id_high", name="uq_dismissal"),
    )


class PlayerRoleConflictConfirmation(Base):
    """Giocatore segnalato con ruoli incompatibili tra stagioni ma
    confermato come UNA SOLA persona reale (es. evoluzione di ruolo in
    carriera): esclude il giocatore dai futuri controlli di /role-conflicts."""
    __tablename__ = "player_role_conflict_confirmations"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, unique=True)
    confirmed_at = Column(DateTime, default=datetime.utcnow)
