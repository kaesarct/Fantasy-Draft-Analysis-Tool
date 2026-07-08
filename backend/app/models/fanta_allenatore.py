"""FantaAllenatore — permanent coach profile across seasons."""
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship
from app.database import Base


class FantaAllenatore(Base):
    __tablename__ = "fanta_allenatori"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(150), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    is_active = Column(Boolean, default=True)

    # Tutte le squadre di questo allenatore nel corso delle stagioni
    team_coaches = relationship("FantaTeamCoach", back_populates="allenatore")
