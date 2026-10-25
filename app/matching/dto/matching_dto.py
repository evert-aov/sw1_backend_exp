from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.experience.entity.experience import ModalityEnum
from app.matching.entity.matching_group import MatchingGroupStatusEnum


class MatchingApplicationDTO(BaseModel):
    """
    Contrato de entrada para postular a un grupo dinámico de matching por afinidad (CU-07 / HU-09).
    """

    experience_id: str = Field(..., description="ID de la experiencia a la que se desea postular")


class MatchingGroupResponseDTO(BaseModel):
    """
    Contrato de respuesta para el estado de un grupo de matching y su progreso hacia el quórum mínimo (CU-07 / HU-08, HU-09).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="ID del grupo de matching")
    experience_id: str = Field(..., description="ID de la experiencia vinculada")
    target_quorum: int = Field(
        ..., description="Mínimo de reservas pagadas requerido por la experiencia; no es una meta de postulaciones"
    )
    current_members: int = Field(
        ..., description="Usuarios postulados a este grupo; no equivale a reservas ni a cupos pagados"
    )
    status: MatchingGroupStatusEnum = Field(
        ..., description="Estado derivado del quórum real o estado del grupo: OPEN, REACHED o EXPIRED"
    )
    deadline: datetime = Field(
        ..., description="Fecha del evento por compatibilidad del esquema; no activa expiración automática"
    )
    created_at: datetime = Field(..., description="Fecha de creación del grupo")
    is_quorum_reached: bool = Field(
        default=False, description="Indica si reservas pagadas alcanzaron el mínimo de la experiencia"
    )


class UnmetDemandInsightDTO(BaseModel):
    """Agregado de búsquedas del catálogo sin resultados por categoría y zona."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(
        ...,
        description=(
            "UUID estable derivado de zona y categoría para identificar este agregado; "
            "no es el ID de una fila materializada en unmet_demands"
        ),
    )
    zone: str = Field(..., description="Zona urbana analizada")
    category_keyword: str = Field(..., description="Nombre canónico de la categoría buscada")
    search_count: int = Field(
        ..., ge=0, description="Eventos de búsqueda sin resultados; no representa personas únicas"
    )
    suggested_price: float | None = Field(
        default=None,
        description="Sin calcular en esta fase; se mantiene por compatibilidad del contrato",
    )
    suggested_time_slot: str | None = Field(
        default=None,
        description="Sin calcular en esta fase; se mantiene por compatibilidad del contrato",
    )
    analyzed_at: datetime = Field(..., description="Fecha de cálculo del agregado")
    window_days: int = Field(..., ge=1, description="Ventana retrospectiva usada para el conteo")


class DemandModelStatusDTO(BaseModel):
    """Estado auditable del clasificador entrenado con resultados transaccionales reales."""

    model_status: str = Field(..., description="TRAINED, INSUFFICIENT_DATA o VALIDATION_FAILED")
    model_version: str | None = Field(default=None, description="Versión lógica del pipeline")
    training_window_days: int = Field(..., ge=1, description="Ventana temporal histórica evaluada")
    training_example_count: int = Field(..., ge=0, description="Eventos reales usados en el dataset")
    positive_example_count: int = Field(..., ge=0, description="Eventos que alcanzaron quórum pagado")
    negative_example_count: int = Field(..., ge=0, description="Eventos con evidencia de pago que no alcanzaron quórum")
    model_currency: str | None = Field(
        default=None,
        description="Moneda única de pagos usada por el modelo; nunca mezcla escalas monetarias",
    )
    validation_example_count: int = Field(..., ge=0, description="Eventos del holdout temporal")
    validation_auc: float | None = Field(default=None, ge=0.0, le=1.0)
    validation_brier_score: float | None = Field(default=None, ge=0.0, le=1.0)
    baseline_brier_score: float | None = Field(default=None, ge=0.0, le=1.0)
    validation_strategy: str = Field(default="TEMPORAL_HOLDOUT_80_20")
    artifact_scope: str = Field(
        default="IN_PROCESS_REBUILT_FROM_DATABASE",
        description="El modelo se conserva en memoria por proceso y puede reconstruirse desde el historial compartido",
    )
    evaluated_at: datetime = Field(..., description="Momento del último entrenamiento o evaluación")
    message: str = Field(..., description="Resultado legible de elegibilidad o validación del modelo")


class SuggestedExperienceDTO(BaseModel):
    """Propuesta explicable con estimación ML solo cuando supera la validación temporal."""

    model_config = ConfigDict(from_attributes=True)

    zone: str = Field(..., description="Zona urbana objetivo")
    category_keyword: str = Field(..., description="Temática sugerida por búsquedas sin resultados")
    estimated_interest_count: int | None = Field(
        default=None,
        description="Sin estimar: los eventos de búsqueda no equivalen a personas interesadas",
    )
    suggested_price: float | None = Field(
        default=None,
        description=(
            "Mediana de precios de experiencias comparables que alcanzaron su quórum con reservas pagadas; "
            "null si no hay suficiente historial"
        ),
    )
    suggested_currency: str | None = Field(
        default=None,
        description="Moneda confirmada por los pagos de las experiencias usadas como referencia",
    )
    recommended_time_slot: str | None = Field(
        default=None,
        description=(
            "Día y franja horaria local más frecuente entre experiencias comparables que alcanzaron el quórum; "
            "null si no hay suficiente historial"
        ),
    )
    recommended_modality: ModalityEnum | None = Field(
        default=None,
        description=(
            "Modalidad más frecuente entre experiencias comparables que alcanzaron el quórum pagado; "
            "null si no hay suficiente historial"
        ),
    )
    historical_quorum_example_count: int = Field(
        ..., ge=0, description="Cantidad de éxitos reales usados como referencia para precio/horario/modalidad"
    )
    historical_outcome_example_count: int = Field(
        ..., ge=0, description="Eventos pasados con registros de pago disponibles para estimar quórum"
    )
    quorum_probability: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Probabilidad de quórum del clasificador validado o fallback bayesiano; null sin evidencia aplicable",
    )
    recommendation_source: str = Field(
        default="INSUFFICIENT_HISTORY",
        description=(
            "TRAINED_LOGISTIC_REGRESSION solo tras validación temporal; HISTORICAL_BAYESIAN como fallback; "
            "INSUFFICIENT_HISTORY si no hay datos aplicables"
        ),
    )
    model: DemandModelStatusDTO = Field(..., description="Muestras y métricas de validación temporal del modelo")
    candidate_reference_scope: str | None = Field(
        default=None,
        description="ZONE_CATEGORY o CATEGORY_CROSS_ZONE según el alcance de los antecedentes usados",
    )
    assumed_min_capacity: int | None = Field(
        default=None, ge=1, description="Aforo mínimo asumido para calcular la probabilidad de quórum"
    )
    assumed_max_capacity: int | None = Field(
        default=None, ge=1, description="Aforo máximo asumido para calcular la probabilidad de quórum"
    )
    confidence_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="No calculado; revisar AUC/Brier y tamaños de muestra en el objeto model",
    )
    observed_search_count: int = Field(
        ..., ge=0, description="Eventos observados de búsqueda sin resultados; no son asistentes potenciales"
    )
    window_days: int = Field(..., ge=1, description="Ventana retrospectiva usada para ordenar sugerencias")
    analyzed_at: datetime = Field(..., description="Momento en que se calculó la sugerencia")


class ExperienceRecommendationDTO(BaseModel):
    """Tarjeta de experiencia recomendada con razones descriptivas, no probabilidad de asistencia."""

    experience_id: str = Field(..., description="UUID de la experiencia")
    title: str = Field(..., description="Título de la experiencia")
    category_name: str | None = Field(default=None, description="Categoría temática")
    cover_image_url: str | None = Field(default=None, description="Imagen de portada")
    modality: str = Field(..., description="Modalidad de la experiencia")
    event_date: datetime = Field(..., description="Fecha de inicio en UTC")
    price: float = Field(..., ge=0, description="Precio publicado por cupo")
    venue_name: str | None = Field(default=None, description="Nombre del venue, si aplica")
    venue_zone: str | None = Field(default=None, description="Zona urbana del venue, si aplica")
    distance_km: float | None = Field(
        default=None,
        ge=0,
        description="Distancia en línea recta desde las coordenadas enviadas; null si no se puede calcular",
    )
    interest_score: float = Field(
        ..., ge=0.0, le=1.0, description="Coincidencia textual determinística con los intereses del perfil"
    )
    matched_interests: list[str] = Field(
        default_factory=list, description="Intereses del perfil que coinciden con esta experiencia"
    )
    reasons: list[str] = Field(default_factory=list, description="Explicaciones legibles del orden de recomendación")


class SearchLogDTO(BaseModel):
    """Contrato legado de búsqueda; found_results solo es confiable cuando lo establece el servidor."""

    model_config = ConfigDict(str_strip_whitespace=True)

    query_text: str | None = Field(default=None, max_length=200, description="Texto libre; no se persiste en esta fase")
    category: str | None = Field(default=None, max_length=100, description="Categoría canónica asociada a la búsqueda")
    zone: str | None = Field(default=None, max_length=100, description="Zona urbana consultada")
    found_results: bool = Field(
        default=True,
        description="Resultado verificado por el catálogo; no se acepta como evidencia del cliente",
    )
