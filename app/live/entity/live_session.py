from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.core.database import Base


class LiveSessionStatusEnum(str, enum.Enum):
    INITIALIZED = "INITIALIZED"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


# Entidad SesiónEnVivo: orquesta la transmisión y telemetría en tiempo real de una experiencia (CU-09)
class LiveSession(Base):
    __tablename__ = "live_sessions"

    id = Column(Integer, primary_key=True, index=True)
    experience_id = Column(Integer, ForeignKey("experiences.id", ondelete="CASCADE"), nullable=False)
    host_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    status = Column(Enum(LiveSessionStatusEnum), default=LiveSessionStatusEnum.INITIALIZED, nullable=False)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)

    # Relaciones
    experience = relationship("app.experience.entity.experience.Experience", back_populates="live_sessions")
    metrics = relationship("AudienceMetric", back_populates="live_session", cascade="all, delete-orphan")
    suggestions = relationship("LiveSuggestion", back_populates="live_session", cascade="all, delete-orphan")
    consents = relationship("Consent", back_populates="live_session", cascade="all, delete-orphan")
