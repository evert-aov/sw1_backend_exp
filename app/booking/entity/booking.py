from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, Enum, UUID
from sqlalchemy.orm import relationship
from app.core.database import Base, generate_uuid


class BookingStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


# Entidad Reserva: registro de cupos adquiridos y comisiones de plataforma (CU-06)
class Booking(Base):
    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    experience_id = Column(UUID(as_uuid=False), ForeignKey("experiences.id", ondelete="CASCADE"), nullable=False)

    quantity = Column(Integer, default=1, nullable=False)
    total_amount = Column(Float, nullable=False)
    platform_fee = Column(Float, default=0.0, nullable=False)  # Comisión escalonada retenida
    host_payout = Column(Float, default=0.0, nullable=False)   # Ganancia neta para el anfitrión

    status = Column(Enum(BookingStatusEnum), default=BookingStatusEnum.PENDING, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relaciones
    user = relationship("app.auth.entity.user.User", back_populates="bookings")
    experience = relationship("app.experience.entity.experience.Experience", back_populates="bookings")
    payment = relationship("Payment", back_populates="booking", uselist=False, cascade="all, delete-orphan")
    tickets = relationship("Ticket", back_populates="booking", cascade="all, delete-orphan")
