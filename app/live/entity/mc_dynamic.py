import enum
from datetime import datetime, timezone

from sqlalchemy import UUID, Boolean, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, generate_uuid


class McDynamicTypeEnum(str, enum.Enum):
    """Tipo de dinámica que el Asistente MC puede proponer al moderador (HU-19)."""

    AUDIENCE_QUESTION = "AUDIENCE_QUESTION"  # Pregunta o interacción breve con el público
    ACTIVE_BREAK = "ACTIVE_BREAK"  # Pausa activa: movimiento, estiramiento o dinámica corporal
    SHORT_BREAK = "SHORT_BREAK"  # Descanso corto para recuperar la atención


class McDynamicModalityEnum(str, enum.Enum):
    """Modalidad de evento en la que la dinámica es aplicable."""

    ANY = "ANY"
    IN_PERSON = "IN_PERSON"
    VIRTUAL = "VIRTUAL"


# Entidad DinámicaMC: catálogo de dinámicas para reactivar la atención (CU-11 / HU-19), cargado por seed
class McDynamic(Base):
    __tablename__ = "mc_dynamics"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=generate_uuid, index=True
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)

    dynamic_type: Mapped[McDynamicTypeEnum] = mapped_column(
        Enum(McDynamicTypeEnum, name="mcdynamictypeenum"), nullable=False
    )
    modality: Mapped[McDynamicModalityEnum] = mapped_column(
        Enum(McDynamicModalityEnum, name="mcdynamicmodalityenum"),
        default=McDynamicModalityEnum.ANY,
        nullable=False,
    )
    # Intensidad: 1 suave · 2 media · 3 reactivación fuerte
    intensity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    title_es: Mapped[str] = mapped_column(String(120), nullable=False)
    title_en: Mapped[str] = mapped_column(String(120), nullable=False)
    instructions_es: Mapped[str] = mapped_column(Text, nullable=False)
    instructions_en: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=True
    )
