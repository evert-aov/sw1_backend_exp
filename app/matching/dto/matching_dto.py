from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.matching.entity.matching_group import MatchingGroupStatusEnum


class MatchingApplicationDTO(BaseModel):
    """
    Contrato de entrada para postular a un grupo dinámico de matching por afinidad (CU-07 / HU-09).
    """

    experience_id: int = Field(..., ge=1, description="ID de la experiencia a la que se desea postular")


class MatchingGroupResponseDTO(BaseModel):
    """
    Contrato de respuesta para el estado de un grupo de matching y su progreso hacia el quórum mínimo (CU-07 / HU-08, HU-09).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID del grupo de matching")
    experience_id: int = Field(..., description="ID de la experiencia vinculada")
    target_quorum: int = Field(..., description="Cantidad mínima de integrantes requerida")
    current_members: int = Field(..., description="Cantidad actual de integrantes agrupados")
    status: MatchingGroupStatusEnum = Field(..., description="Estado del grupo: OPEN, REACHED o EXPIRED")
    deadline: datetime = Field(..., description="Fecha límite para consolidar el quórum")
    created_at: datetime = Field(..., description="Fecha de creación del grupo")
    is_quorum_reached: bool = Field(default=False, description="Indica si se alcanzó el quórum mínimo")


class UnmetDemandInsightDTO(BaseModel):
    """
    Contrato de respuesta con analítica de demanda urbana insatisfecha por zona geográfica (CU-08 / HU-10).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID del registro de demanda insatisfecha")
    zone: str = Field(..., description="Zona urbana analizada")
    category_keyword: str = Field(..., description="Categoría o término buscado sin cobertura")
    search_count: int = Field(..., description="Volumen acumulado de búsquedas insatisfechas")
    suggested_price: float | None = Field(default=None, description="Precio promedio sugerido")
    suggested_time_slot: str | None = Field(default=None, description="Franja horaria recomendada")
    analyzed_at: datetime = Field(..., description="Fecha de última actualización analítica")


class SuggestedExperienceDTO(BaseModel):
    """
    Contrato de respuesta con recomendaciones de creación de eventos rentables para establecimientos (CU-08 / HU-11).
    """

    model_config = ConfigDict(from_attributes=True)

    zone: str = Field(..., description="Zona urbana objetivo")
    category_keyword: str = Field(..., description="Temática sugerida")
    estimated_interest_count: int = Field(..., description="Demanda potencial estimada")
    suggested_price: float = Field(..., description="Precio de entrada sugerido")
    recommended_time_slot: str = Field(..., description="Horario recomendado para mayor asistencia")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Nivel de confianza predictiva (0.0 a 1.0)")


class SearchLogDTO(BaseModel):
    """
    Contrato de datos para registrar búsquedas de usuarios en el motor de prospección de demanda (CU-08).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    query_text: str | None = Field(default=None, max_length=200, description="Texto libre buscado")
    category: str | None = Field(default=None, max_length=100, description="Categoría filtrada")
    zone: str | None = Field(default=None, max_length=100, description="Zona geográfica consultada")
    found_results: bool = Field(default=True, description="Indica si la búsqueda arrojó resultados")
