from __future__ import annotations

import enum
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.live.entity.audience_metric import AgeGroupEnum


class EnergyTrafficLightEnum(str, enum.Enum):
    """Niveles del semáforo discreto de energía de la audiencia (HU-17)."""

    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class EnergyTrendEnum(str, enum.Enum):
    """Dirección reciente del índice de energía suavizado (HU-17)."""

    RISING = "RISING"
    STABLE = "STABLE"
    FALLING = "FALLING"


class SignalStatusEnum(str, enum.Enum):
    """
    Estado de la señal de telemetría de la sesión (HU-17).

    LIVE: llegó una métrica en los últimos 7.5 s. STALE: la última métrica tiene hasta 30 s.
    NO_SIGNAL: no hay métricas recientes (cámara apagada o sin muestreo activo).
    """

    LIVE = "LIVE"
    STALE = "STALE"
    NO_SIGNAL = "NO_SIGNAL"


class PulsePointDTO(BaseModel):
    """Punto de la gráfica de pulso de energía de la consola en vivo (HU-17)."""

    model_config = ConfigDict(from_attributes=True)

    recorded_at: datetime = Field(..., description="Instante de la métrica agregada que originó el punto")
    energy_score: float = Field(..., ge=0.0, le=1.0, description="Índice de energía suavizado (0.0 a 1.0)")
    traffic_light: EnergyTrafficLightEnum = Field(..., description="Color del semáforo en ese instante")


class LiveTelemetrySnapshotDTO(BaseModel):
    """
    Instantánea de telemetría agregada emitida cada 2.5 s a la consola del anfitrión (CU-09 / HU-17).

    Contiene solo valores numéricos agregados: nunca imágenes ni datos de personas (GDPR).
    """

    model_config = ConfigDict(from_attributes=True)

    type: Literal["telemetry"] = Field(default="telemetry", description="Tipo de mensaje del canal WebSocket")
    session_id: str = Field(..., description="ID de la sesión en vivo")
    emitted_at: datetime = Field(..., description="Instante de emisión de la instantánea (UTC)")
    interval_seconds: float = Field(..., gt=0, description="Intervalo de emisión sincronizada en segundos")
    signal_status: SignalStatusEnum = Field(..., description="Estado de la señal: LIVE, STALE o NO_SIGNAL")
    energy_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Índice de energía suavizado; null si nunca hubo métricas"
    )
    traffic_light: EnergyTrafficLightEnum | None = Field(
        default=None, description="Semáforo de energía GREEN/YELLOW/RED; null si nunca hubo métricas"
    )
    trend: EnergyTrendEnum = Field(default=EnergyTrendEnum.STABLE, description="Tendencia reciente de la energía")
    attention_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Última atención promedio")
    joy_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Última alegría promedio")
    detected_faces_count: int | None = Field(default=None, ge=0, description="Rostros detectados en la última métrica")
    dominant_age_group: AgeGroupEnum | None = Field(default=None, description="Rango etario predominante")
    last_metric_at: datetime | None = Field(default=None, description="Instante de la última métrica recibida")
    pulse: list[PulsePointDTO] = Field(
        default_factory=list, description="Últimos puntos de energía (ventana de 60 s) para la gráfica de pulso"
    )


class MonitorCodeDTO(BaseModel):
    """Código de un solo uso para vincular una tablet o celular como monitor de la sesión (HU-17)."""

    code: str = Field(..., min_length=6, max_length=6, description="Código de 6 caracteres a ingresar en la app")
    session_id: str = Field(..., description="ID de la sesión en vivo vinculada")
    expires_in_seconds: int = Field(..., gt=0, description="Segundos de validez del código")


class MonitorRedeemDTO(BaseModel):
    """Solicitud de canje de un código de monitor desde la app móvil (HU-17)."""

    code: str = Field(..., min_length=6, max_length=12, description="Código mostrado en la consola web")


class MonitorTokenDTO(BaseModel):
    """Token de solo lectura que permite al dispositivo observar la telemetría de una sesión (HU-17)."""

    access_token: str = Field(..., description="Token de monitor; no sirve para otros endpoints de la API")
    token_type: Literal["monitor"] = Field(default="monitor", description="Tipo de token")
    session_id: str = Field(..., description="ID de la sesión en vivo que puede observar")
    experience_title: str = Field(..., description="Título de la experiencia transmitida")
    expires_at: datetime = Field(..., description="Fecha de expiración del token en UTC")
