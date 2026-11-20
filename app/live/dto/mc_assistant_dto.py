from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.live.entity.mc_alert import McAlertStatusEnum, McAlertTriggerEnum
from app.live.entity.mc_dynamic import McDynamicModalityEnum, McDynamicTypeEnum


class McDynamicDTO(BaseModel):
    """Dinámica del catálogo del Asistente MC, con textos en español e inglés (HU-19)."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="ID de la dinámica")
    code: str = Field(..., description="Código estable de la dinámica")
    dynamic_type: McDynamicTypeEnum = Field(
        ..., description="AUDIENCE_QUESTION, ACTIVE_BREAK o SHORT_BREAK"
    )
    modality: McDynamicModalityEnum = Field(
        ..., description="Modalidad aplicable: ANY, IN_PERSON o VIRTUAL"
    )
    intensity: int = Field(..., ge=1, le=3, description="1 suave, 2 media, 3 reactivación fuerte")
    duration_minutes: int = Field(..., ge=0, description="Duración estimada en minutos")
    category_names: list[str] = Field(
        default_factory=list, description="Categorías de experiencia; vacía = dinámica general"
    )
    title_es: str = Field(..., description="Título en español")
    title_en: str = Field(..., description="Título en inglés")
    instructions_es: str = Field(..., description="Instrucciones en español")
    instructions_en: str = Field(..., description="Instrucciones en inglés")


class McAlertDTO(BaseModel):
    """Alerta de desatención sostenida con la dinámica propuesta (HU-18 / HU-19)."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="ID de la alerta")
    session_id: str = Field(..., description="ID de la sesión en vivo")
    trigger: McAlertTriggerEnum = Field(..., description="SUSTAINED_INATTENTION o MANUAL_REQUEST")
    status: McAlertStatusEnum = Field(..., description="ACTIVE, APPLIED, DISMISSED o EXPIRED")
    average_attention: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Atención media de la caída"
    )
    low_attention_seconds: int = Field(..., ge=0, description="Segundos de atención baja sostenida")
    created_at: datetime = Field(..., description="Instante de emisión (UTC)")
    resolved_at: datetime | None = Field(
        default=None, description="Instante de respuesta o vencimiento (UTC)"
    )
    break_ends_at: datetime | None = Field(
        default=None, description="Fin de la pausa si se aplicó un descanso (UTC)"
    )
    suggestion_id: str | None = Field(
        default=None, description="ID de la sugerencia registrada en live_suggestions"
    )
    dynamic: McDynamicDTO | None = Field(default=None, description="Dinámica propuesta")


class McAlertEventDTO(BaseModel):
    """Mensaje del canal WebSocket de telemetría cuando una alerta MC se crea o cambia de estado."""

    type: Literal["mc_alert"] = Field(default="mc_alert", description="Tipo de mensaje del canal")
    alert: McAlertDTO = Field(..., description="Estado vigente de la alerta")


class PushDeviceRegisterDTO(BaseModel):
    """Registro del token de Firebase del monitor vinculado para recibir alertas push (HU-18)."""

    fcm_token: str = Field(
        ..., min_length=20, max_length=512, description="Token de Firebase Cloud Messaging"
    )
    platform: Literal["android", "ios", "web"] = Field(
        default="android", description="Plataforma del dispositivo"
    )
    language: Literal["es", "en"] = Field(default="es", description="Idioma de las notificaciones")


class PushDeviceRemoveDTO(BaseModel):
    """Baja del token de Firebase cuando el monitor se desvincula (HU-18)."""

    fcm_token: str = Field(
        ..., min_length=20, max_length=512, description="Token de Firebase Cloud Messaging"
    )


class PushDeviceRegisteredDTO(BaseModel):
    """Resultado del registro del dispositivo para notificaciones push."""

    registered: bool = Field(..., description="Verdadero si el dispositivo quedó registrado")
    push_enabled: bool = Field(
        ..., description="Falso si el servidor no tiene Firebase configurado"
    )
    expires_at: datetime = Field(
        ..., description="Hasta cuándo recibirá alertas (expiración del monitor)"
    )


class McAiModelInfoDTO(BaseModel):
    """Información de disponibilidad de un modelo de IA configurado para el Asistente MC."""

    provider: Literal["vertex", "ollama"] = Field(..., description="Proveedor de inferencia")
    id: str = Field(..., description="Identificador del modelo (ej. gemini-3.8-flash o qwen3.8:latest)")
    label: str = Field(..., description="Nombre legible para el selector de la interfaz")
    available: bool = Field(..., description="Verdadero si el modelo está configurado/accesible")


class McAiCatalogDTO(BaseModel):
    """Catálogo de modelos disponibles para el chat del Asistente MC."""

    default_provider: Literal["vertex", "ollama"] = Field(..., description="Proveedor por defecto")
    models: list[McAiModelInfoDTO] = Field(default_factory=list, description="Modelos disponibles")


class McAiChatMessageDTO(BaseModel):
    """Turno previo de conversación en el chat del Asistente MC."""

    role: Literal["user", "assistant"] = Field(..., description="Emisor del mensaje")
    content: str = Field(..., min_length=1, max_length=6000, description="Contenido del mensaje")


class McAiTelemetryContextDTO(BaseModel):
    """Instantánea opcional de telemetría enviada por el cliente cuando aún no hay sesión persistida."""

    signal_status: str | None = None
    traffic_light: str | None = None
    energy_score: float | None = None
    attention_score: float | None = None
    joy_score: float | None = None
    inattention_score: float | None = None
    detected_faces_count: int | None = None
    trend: str | None = None
    dominant_age_group: str | None = None


class McAiChatRequestDTO(BaseModel):
    """Solicitud de mensaje al chat conversacional del Asistente MC con IA."""

    message: str = Field(..., min_length=1, max_length=4000, description="Mensaje del anfitrión")
    provider: Literal["vertex", "ollama"] | None = Field(
        default=None, description="Proveedor elegido: vertex (Gemini) u ollama (Qwen 3.8)"
    )
    language: Literal["es", "en"] = Field(default="es", description="Idioma de respuesta")
    history: list[McAiChatMessageDTO] = Field(
        default_factory=list, description="Historial reciente del chat"
    )
    telemetry: McAiTelemetryContextDTO | None = Field(
        default=None, description="Contexto en vivo de métricas de audiencia"
    )


class McAiChatResponseDTO(BaseModel):
    """Respuesta generada por el Asistente MC con IA."""

    reply: str = Field(..., description="Respuesta del asistente en texto/markdown ligero")
    speech_text: str | None = Field(
        default=None,
        description="Guion limpio listo para locución directa al público sin títulos ni acotaciones",
    )
    provider: Literal["vertex", "ollama"] = Field(..., description="Proveedor utilizado")
    model: str = Field(..., description="Modelo exacto que respondió")
    input_tokens: int | None = Field(default=None, description="Tokens de entrada")
    output_tokens: int | None = Field(default=None, description="Tokens de salida")


class McAiStoredMessageDTO(BaseModel):
    """Mensaje persistido en la memoria del chat por evento."""

    id: str = Field(..., description="ID único del mensaje")
    role: Literal["user", "assistant"] = Field(..., description="Emisor del mensaje")
    content: str = Field(..., description="Contenido del mensaje")
    provider: Literal["vertex", "ollama"] | None = Field(default=None, description="Proveedor IA")
    model: str | None = Field(default=None, description="Modelo utilizado")
    created_at: datetime = Field(..., description="Instante de registro (UTC)")


class McAiChatHistoryDTO(BaseModel):
    """Historial de conversación persistido para un evento y su título."""

    event_key: str = Field(..., description="Clave canónica del evento")
    event_title: str | None = Field(default=None, description="Nombre del evento si existe")
    event_status: str | None = Field(default=None, description="Estado actual del evento (OPEN, CONFIRMED, LIVE, FINISHED)")
    live_session_id: str | None = Field(default=None, description="UUID de la sesión en vivo activa, si existe")
    messages: list[McAiStoredMessageDTO] = Field(
        default_factory=list, description="Mensajes guardados en orden cronológico"
    )


class McWelcomeSpeechRequestDTO(BaseModel):
    """Solicitud para generar 2 propuestas de discurso de bienvenida del Maestro de Ceremonias."""

    provider: Literal["vertex", "ollama"] | None = Field(default=None)
    language: Literal["es", "en"] = Field(default="es")


class McWelcomeSpeechOptionDTO(BaseModel):
    """Una propuesta de discurso de bienvenida lista para aprobar y locutar."""

    id: str
    style: str
    title: str
    speech_text: str


class McWelcomeSpeechesResponseDTO(BaseModel):
    """Par de propuestas de discurso de bienvenida generadas por la IA."""

    options: list[McWelcomeSpeechOptionDTO]
    provider: Literal["vertex", "ollama"]
    model: str


class McAutonomousSuggestionRequestDTO(BaseModel):
    """Solicitud periódica (cada minuto) para que el MC evalúe métricas y proponga una intervención."""

    provider: Literal["vertex", "ollama"] | None = Field(default=None)
    language: Literal["es", "en"] = Field(default="es")
    telemetry: McAiTelemetryContextDTO | None = Field(default=None)


class McAutonomousSuggestionResponseDTO(BaseModel):
    """Intervención propuesta de forma autónoma por el MC, pendiente de aprobación para hablar."""

    title: str
    reason: str
    speech_text: str
    provider: Literal["vertex", "ollama"]
    model: str


class McSpeechRequestDTO(BaseModel):
    """Solicitud para sintetizar en audio (Edge TTS) una locución del Maestro de Ceremonias."""

    text: str = Field(..., min_length=1, max_length=6000)
    voice: Literal["marcelo", "sofia", "andrew"] = Field(default="marcelo")
    language: Literal["es", "en"] = Field(default="es")
    record_in_session_id: str | None = Field(
        default=None,
        description="Si se envía, guarda la locución aprobada en la memoria del evento",
    )
    provider: Literal["vertex", "ollama"] | None = Field(default=None)
    model: str | None = Field(default=None)


class DjTransitionRequestDTO(BaseModel):
    """Solicitud al DJ Autónomo para recomendar playlist/BPM y frase de micrófono."""

    provider: Literal["vertex", "ollama"] | None = Field(default=None)
    language: Literal["es", "en"] = Field(default="es")
    current_playlist_id: str | None = Field(default=None)
    telemetry: McAiTelemetryContextDTO | None = Field(default=None)


class DjYoutubeTrackDTO(BaseModel):
    """Resultado musical embebible devuelto por YouTube Data API v3."""

    video_id: str
    title: str
    channel: str
    thumbnail: str = ""


class DjYoutubeSearchResponseDTO(BaseModel):
    """Respuesta de búsqueda musical en YouTube."""

    query: str
    tracks: list[DjYoutubeTrackDTO] = Field(default_factory=list)


class DjTransitionResponseDTO(BaseModel):
    """Transición musical sugerida por el DJ Autónomo con frase lista para locución."""

    recommended_playlist_id: Literal[
        "chill_jazz", "groove_funk", "melodic_house", "upbeat_party"
    ]
    recommended_genre: str
    recommended_bpm: str
    youtube_search_query: str | None = None
    youtube_tracks: list[DjYoutubeTrackDTO] = Field(default_factory=list)
    reason: str
    dj_shoutout: str
    provider: Literal["vertex", "ollama"]
    model: str
