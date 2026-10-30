"""Recepción idempotente de eventos Stripe sin guardar cuerpos con datos personales."""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, String
from app.core.database import Base


class StripeEvent(Base):
    """El ID del proveedor se confirma en la misma transacción que el efecto local."""

    __tablename__ = "stripe_events"
    id = Column(String(255), primary_key=True)
    event_type = Column(String(100), nullable=False)
    object_id = Column(String(255), nullable=False)
    outcome = Column(String(40), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
