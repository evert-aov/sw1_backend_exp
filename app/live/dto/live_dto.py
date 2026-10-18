from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.live.entity.audience_metric import AgeGroupEnum
from app.live.entity.live_suggestion import SuggestionTypeEnum


class LiveSessionCreateDTO(BaseModel):
    """
    Contrato de datos para iniciar una sesión de telemetría en vivo de una experiencia (CU-09).
    """

    experience_id: int = Field(..., ge=1, description="ID de la experiencia que inicia transmisión en vivo")


class FramePayloadDTO(BaseModel):
    """
    Contrato de datos para un fotograma efímero muestreado cada 2-3 segundos y procesado solo en RAM (CU-09 / HU-13, HU-14).
    """

    session_id: int = Field(..., ge=1, description="ID de la sesión en vivo activa")
    image_base64: str = Field(..., description="Fotograma codificado en Base64 (descartado de RAM tras inferencia)")
    timestamp_ms: int = Field(..., ge=0, description="Marca de tiempo del fotograma en milisegundos")


class LiveMetricsDTO(BaseModel):
    """
    Contrato de respuesta con las métricas agregadas de audiencia transmitidas al Dashboard Smart Host (CU-10 / HU-15, HU-16, HU-17).
    """

    model_config = ConfigDict(from_attributes=True)

    session_id: int = Field(..., description="ID de la sesión en vivo")
    recorded_at: datetime = Field(..., description="Fecha y hora de la medición")
    detected_faces_count: int = Field(..., ge=0, description="Cantidad de rostros detectados de forma anónima")
    attention_score: float = Field(..., ge=0.0, le=1.0, description="Índice de atención promedio (0.0 a 1.0)")
    joy_score: float = Field(..., ge=0.0, le=1.0, description="Índice de entusiasmo/alegría (0.0 a 1.0)")
    neutral_score: float = Field(..., ge=0.0, le=1.0, description="Índice de expresión neutral (0.0 a 1.0)")
    inattention_score: float = Field(..., ge=0.0, le=1.0, description="Índice de desatención (0.0 a 1.0)")
    dominant_age_group: AgeGroupEnum | None = Field(
        default=None,
        description="Rango etario predominante estimado en la audiencia",
    )
    energy_traffic_light: str = Field(..., description="Semáforo visual de energía: GREEN, YELLOW o RED")


class ActionSuggestionDTO(BaseModel):
    """
    Contrato de respuesta para las sugerencias en tiempo real del Asistente MC y DJ Virtual (CU-11, CU-12 / HU-18..HU-21).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID único de la sugerencia")
    session_id: int = Field(..., description="ID de la sesión en vivo")
    suggestion_type: SuggestionTypeEnum = Field(..., description="Tipo de sugerencia: MC_DYNAMIC, DJ_MUSIC_CHANGE, BREAK")
    suggestion_text: str = Field(..., description="Descripción de la dinámica o acción recomendada")
    recommended_bpm: str | None = Field(default=None, description="Rango de BPM sugerido para el DJ")
    recommended_genre: str | None = Field(default=None, description="Género musical sugerido")
    applied: bool = Field(default=False, description="Indica si la sugerencia fue aplicada por el anfitrión")
    created_at: datetime = Field(..., description="Fecha y hora de emisión de la sugerencia")


class MetricTimelinePointDTO(BaseModel):
    """
    Punto de serie temporal minuto a minuto para la gráfica del reporte post-evento (CU-13 / HU-22).
    """

    model_config = ConfigDict(from_attributes=True)

    minute: int = Field(..., ge=0, description="Minuto transcurrido de la sesión")
    average_attention: float = Field(..., ge=0.0, le=1.0, description="Atención promedio en ese minuto")
    average_joy: float = Field(..., ge=0.0, le=1.0, description="Entusiasmo promedio en ese minuto")
    dominant_age: str | None = Field(default=None, description="Grupo etario dominante en ese minuto")


class PostEventReportDTO(BaseModel):
    """
    Contrato de respuesta para el reporte analítico post-evento con curva de energía minuto a minuto (CU-13 / HU-22).
    """

    model_config = ConfigDict(from_attributes=True)

    session_id: int = Field(..., description="ID de la sesión analizada")
    experience_id: int = Field(..., description="ID de la experiencia")
    experience_title: str = Field(..., description="Título de la experiencia")
    total_duration_minutes: int = Field(..., ge=0, description="Duración total registrada en minutos")
    average_attention_score: float = Field(..., ge=0.0, le=1.0, description="Promedio global de atención")
    average_joy_score: float = Field(..., ge=0.0, le=1.0, description="Promedio global de entusiasmo")
    peak_engagement_minute: int = Field(..., ge=0, description="Minuto donde se alcanzó el pico máximo de energía")
    timeline: list[MetricTimelinePointDTO] = Field(
        default_factory=list,
        description="Serie de tiempo minuto a minuto de la sesión",
    )


class ConsentDTO(BaseModel):
    """
    Contrato de datos para registrar el consentimiento informado GDPR de análisis efímero en RAM (HU-14).
    """

    session_id: int = Field(..., ge=1, description="ID de la sesión en vivo")
    accepted: bool = Field(..., description="Confirmación de aceptación del asistente")
    consent_type: str = Field(
        default="GDPR_EPHEMERAL_VIDEO_ANALYSIS",
        description="Tipo de consentimiento bajo normativa GDPR",
    )
