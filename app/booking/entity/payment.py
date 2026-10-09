from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class PaymentStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


# Entidad Pago: integración con pasarela de pagos Stripe (CU-06)
class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), unique=True, nullable=False)

    stripe_payment_intent_id = Column(String(100), unique=True, nullable=True, index=True)
    stripe_checkout_session_id = Column(String(100), nullable=True, index=True)

    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")
    status = Column(Enum(PaymentStatusEnum), default=PaymentStatusEnum.PENDING, nullable=False)
    payment_metadata = Column(JSON, default=dict)

    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    booking = relationship("Booking", back_populates="payment")
