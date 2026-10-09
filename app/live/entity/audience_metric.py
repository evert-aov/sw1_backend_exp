from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.core.database import Base


class AgeGroupEnum(str, enum.Enum):
    YOUTH = "YOUTH"               # < 18
    YOUNG_ADULT = "YOUNG_ADULT"   # 18 - 30
    ADULT = "ADULT"               # 31 - 50
    SENIOR = "SENIOR"             # > 50


# Entidad MétricaAudiencia: almacena agregaciones numéricas efímeras (GDPR - nunca fotos ni rostros)
class AudienceMetric(Base):
    __tablename__ = "audience_metrics"

    id = Column(Integer, primary_key=True, index=True)
    live_session_id = Column(Integer, ForeignKey("live_sessions.id", ondelete="CASCADE"), nullable=False)

    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    detected_faces_count = Column(Integer, default=0, nullable=False)

    attention_score = Column(Float, default=0.0, nullable=False)    # 0.0 a 1.0 (Engagement)
    joy_score = Column(Float, default=0.0, nullable=False)          # 0.0 a 1.0
    neutral_score = Column(Float, default=0.0, nullable=False)      # 0.0 a 1.0
    inattention_score = Column(Float, default=0.0, nullable=False)  # 0.0 a 1.0

    dominant_age_group = Column(Enum(AgeGroupEnum), default=AgeGroupEnum.YOUNG_ADULT, nullable=True)

    live_session = relationship("LiveSession", back_populates="metrics")
