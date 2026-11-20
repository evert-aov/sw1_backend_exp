import enum
from datetime import datetime, timezone

from sqlalchemy import UUID, DateTime, Enum, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, generate_uuid


class McAlertTriggerEnum(str, enum.Enum):
    """Origen de la alerta del Asistente MC (HU-18)."""

    SUSTAINED_INATTENTION = "SUSTAINED_INATTENTION"  # Atención baja de forma sostenida
    MANUAL_REQUEST = "MANUAL_REQUEST"  # El moderador pidió una dinámica


class McAlertStatusEnum(str, enum.Enum):
    """Estado de la alerta y de la dinámica sugerida (HU-18 / HU-19)."""

    ACTIVE = "ACTIVE"  # Visible para el moderador, sin respuesta
    APPLIED = "APPLIED"  # El moderador aplicó la dinámica
    DISMISSED = "DISMISSED"  # El moderador descartó la sugerencia
    EXPIRED = "EXPIRED"  # La atención se recuperó sola antes de responder


# Entidad AlertaMC: alerta de desatención sostenida y dinámica propuesta (CU-11 / HU-18, HU-19)
class McAlert(Base):
    __tablename__ = "mc_alerts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True
    )
    live_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("live_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dynamic_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("mc_dynamics.id", ondelete="SET NULL"), nullable=True
    )
    suggestion_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("live_suggestions.id", ondelete="SET NULL"), nullable=True
    )

    trigger: Mapped[McAlertTriggerEnum] = mapped_column(
        Enum(McAlertTriggerEnum, name="mcalerttriggerenum"), nullable=False
    )
    status: Mapped[McAlertStatusEnum] = mapped_column(
        Enum(McAlertStatusEnum, name="mcalertstatusenum"),
        default=McAlertStatusEnum.ACTIVE,
        nullable=False,
    )

    # Atención media durante la caída (0.0 a 1.0)
    average_attention: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_attention_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Fin de la pausa si la dinámica aplicada es un descanso
    break_ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
