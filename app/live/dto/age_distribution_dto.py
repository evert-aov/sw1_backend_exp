"""Contratos de la estimación etaria del público en vivo (HU-16)."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.live.entity.audience_metric import AgeGroupEnum


class AgeGroupShareDTO(BaseModel):
    """
    Participación de un rango etario dentro de la ventana deslizante de una sesión en vivo (HU-16).
    """

    model_config = ConfigDict(from_attributes=True)

    age_group: AgeGroupEnum = Field(
        ...,
        description="Rango etario: YOUTH (<18), YOUNG_ADULT (18-30), ADULT (31-50) o SENIOR (>50)",
    )
    percentage: float = Field(
        ..., ge=0.0, le=100.0, description="Porcentaje del rango sobre los rostros clasificados (0 a 100)"
    )
    count: int = Field(..., ge=0, description="Rostros clasificados en este rango dentro de la ventana")


class AgeDistributionDTO(BaseModel):
    """
    Contrato de respuesta con la última distribución porcentual de rangos etarios de una sesión (HU-16).

    Solo contiene conteos agregados: ningún fotograma, rostro ni identificador de persona.
    """

    model_config = ConfigDict(from_attributes=True)

    session_id: str = Field(..., description="ID de la sesión en vivo")
    window_seconds: int = Field(..., ge=1, description="Duración de la ventana deslizante en segundos")
    sample_count: int = Field(
        ..., ge=0, description="Fotogramas analizados dentro de la ventana, incluidos los que no tenían rostros"
    )
    detections_count: int = Field(
        ...,
        ge=0,
        description=(
            "Rostros clasificados acumulados en la ventana. Una misma persona cuenta una vez por fotograma; "
            "no representa personas únicas."
        ),
    )
    distribution: list[AgeGroupShareDTO] = Field(
        default_factory=list,
        description="Los cuatro rangos etarios en orden fijo: YOUTH, YOUNG_ADULT, ADULT, SENIOR",
    )
    dominant_age_group: AgeGroupEnum | None = Field(
        default=None, description="Rango con más rostros en la ventana; null si no hay rostros clasificados"
    )
    updated_at: datetime | None = Field(
        default=None, description="Fecha y hora UTC del último fotograma considerado; null si la ventana está vacía"
    )
    estimator_configured: bool = Field(
        ..., description="Indica si el servidor tiene un modelo de estimación de edad registrado"
    )
