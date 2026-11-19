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


class PushDeviceRegisteredDTO(BaseModel):
    """Resultado del registro del dispositivo para notificaciones push."""

    registered: bool = Field(..., description="Verdadero si el dispositivo quedó registrado")
    push_enabled: bool = Field(
        ..., description="Falso si el servidor no tiene Firebase configurado"
    )
    expires_at: datetime = Field(
        ..., description="Hasta cuándo recibirá alertas (expiración del monitor)"
    )
