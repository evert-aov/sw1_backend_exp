from datetime import datetime, timezone

from sqlalchemy import UUID, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, generate_uuid


# Entidad DispositivoMonitor: celular o tablet vinculado que recibe notificaciones push del MC (HU-18)
class MonitorPushDevice(Base):
    __tablename__ = "monitor_push_devices"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True
    )
    live_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("live_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Token de Firebase Cloud Messaging del dispositivo
    fcm_token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="android")
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="es")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    # Igual a la expiración del token de monitor
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
