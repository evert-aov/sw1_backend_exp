from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base, generate_uuid


# Entidad Consentimiento: registro de aceptación de política GDPR para muestreo de video en vivo
class Consent(Base):
    __tablename__ = "consents"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    live_session_id = Column(UUID(as_uuid=False), ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    accepted = Column(Boolean, default=True, nullable=False)
    consent_type = Column(String(100), default="GDPR_EPHEMERAL_VIDEO_ANALYSIS", nullable=False)
    consented_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    live_session = relationship("LiveSession", back_populates="consents")
    user = relationship("app.auth.entity.user.User", back_populates="consents")
