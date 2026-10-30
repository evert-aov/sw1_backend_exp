"""Avisos propios persistentes, deduplicados y recuperables al reconectar."""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UUID
from app.core.database import Base, generate_uuid


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    experience_id = Column(UUID(as_uuid=False), ForeignKey("experiences.id", ondelete="CASCADE"), nullable=False)
    dedupe_key = Column(String(200), unique=True, nullable=False)
    kind = Column(String(40), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    read_at = Column(DateTime(timezone=True), nullable=True)
