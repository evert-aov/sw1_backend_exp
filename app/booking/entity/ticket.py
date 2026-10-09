from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


# Entidad Ticket: entrada digital generada por cada cupo adquirido con código QR único
class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)

    ticket_code = Column(String(64), unique=True, default=lambda: str(uuid.uuid4()), nullable=False, index=True)
    qr_payload = Column(Text, nullable=False)  # Información serializada/firmada para el QR
    is_used = Column(Boolean, default=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    booking = relationship("Booking", back_populates="tickets")
