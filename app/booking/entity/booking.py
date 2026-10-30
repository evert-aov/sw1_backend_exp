from datetime import datetime, timezone
import enum
from sqlalchemy import CheckConstraint, Column, Integer, Numeric, String, DateTime, ForeignKey, Enum, UUID, UniqueConstraint
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
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_booking_user_idempotency"),
        CheckConstraint("quantity > 0", name="ck_booking_positive_quantity"),
        CheckConstraint("total_amount >= 0 AND platform_fee >= 0 AND host_payout >= 0", name="ck_booking_nonnegative_amounts"),
        CheckConstraint("total_amount = platform_fee + host_payout", name="ck_booking_balanced_amounts"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    experience_id = Column(UUID(as_uuid=False), ForeignKey("experiences.id", ondelete="CASCADE"), nullable=False)

    quantity = Column(Integer, default=1, nullable=False)
    total_amount = Column(Numeric(14, 2), nullable=False)
    platform_fee = Column(Numeric(14, 2), default=0, nullable=False)
    host_payout = Column(Numeric(14, 2), default=0, nullable=False)
    unit_price = Column(Numeric(14, 2), nullable=True)
    commission_rate = Column(Numeric(5, 4), nullable=True)
    currency = Column(String(3), nullable=False, default="BOB")
    idempotency_key = Column(String(64), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    cancellation_reason = Column(String(40), nullable=True)

    status = Column(Enum(BookingStatusEnum), default=BookingStatusEnum.PENDING, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relaciones
    user = relationship("app.auth.entity.user.User", back_populates="bookings")
    experience = relationship("app.experience.entity.experience.Experience", back_populates="bookings")
    payment = relationship("Payment", back_populates="booking", uselist=False, cascade="all, delete-orphan")
    tickets = relationship("Ticket", back_populates="booking", cascade="all, delete-orphan")
