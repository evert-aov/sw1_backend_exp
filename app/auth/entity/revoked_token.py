"""Persistencia compartida de revocaciones JWT sin almacenar el token original."""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, String
from app.core.database import Base


class RevokedToken(Base):
    """Huella SHA-256 de un JWT revocado hasta su fecha de expiración."""

    __tablename__ = "revoked_tokens"
    token_hash = Column(String(64), primary_key=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
