from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, Enum, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base, generate_uuid


# Modalidad de la experiencia
class ModalityEnum(str, enum.Enum):
    IN_PERSON = "IN_PERSON"
    VIRTUAL = "VIRTUAL"
    HYBRID = "HYBRID"


# Ciclo de vida y quórum de la experiencia
class ExperienceStatusEnum(str, enum.Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"               # En captación / matching
    CONFIRMED = "CONFIRMED"     # Quórum mínimo alcanzado
    LIVE = "LIVE"               # En desarrollo con telemetría en vivo
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


# Entidad Experiencia: evento con cupo limitado, aforo mínimo y precio (CU-03, CU-04, CU-05)
class Experience(Base):
    __tablename__ = "experiences"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    host_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(UUID(as_uuid=False), ForeignKey("categories.id"), nullable=False)
    venue_id = Column(UUID(as_uuid=False), ForeignKey("venues.id", ondelete="SET NULL"), nullable=True)

    title = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=False)
    cover_image_url = Column(String(255), nullable=True)

    modality = Column(Enum(ModalityEnum), default=ModalityEnum.IN_PERSON, nullable=False)
    status = Column(Enum(ExperienceStatusEnum), default=ExperienceStatusEnum.OPEN, nullable=False)

    price = Column(Float, default=0.0, nullable=False)  # Precio por cupo
    min_capacity = Column(Integer, default=5, nullable=False)  # Quórum mínimo
    max_capacity = Column(Integer, default=20, nullable=False)  # Cupo límite
    reserved_slots = Column(Integer, default=0, nullable=False)

    event_date = Column(DateTime, nullable=False, index=True)
    duration_minutes = Column(Integer, default=120)
    virtual_meeting_url = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relaciones
    category = relationship("Category", back_populates="experiences")
    host = relationship("app.auth.entity.user.User", back_populates="experiences")
    venue = relationship("Venue", back_populates="experiences")
    bookings = relationship("app.booking.entity.booking.Booking", back_populates="experience")
    matching_groups = relationship("app.matching.entity.matching_group.MatchingGroup", back_populates="experience")
    live_sessions = relationship("app.live.entity.live_session.LiveSession", back_populates="experience")
