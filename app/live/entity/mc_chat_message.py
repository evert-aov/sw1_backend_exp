from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

from app.core.database import generate_uuid

McChatBase = declarative_base()


# Entidad MensajeChatMC: memoria conversacional persistente del Asistente MC por evento
class McChatMessage(McChatBase):
    __tablename__ = "mc_chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid, index=True)
    # Clave canónica del evento (experience.id si existe, o session_id como respaldo)
    event_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(24), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
