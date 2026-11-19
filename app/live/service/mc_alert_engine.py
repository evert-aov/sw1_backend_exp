"""
Motor de reglas del Asistente de Maestro de Ceremonias (CU-11 / HU-18, HU-19).

Funciones y clases puras, sin red ni base de datos:
- `InattentionTracker` sigue la racha de atención baja de una sesión con tolerancia a repuntes breves.
- `choose_dynamic` elige la dinámica más adecuada del catálogo según modalidad y gravedad.
"""

from __future__ import annotations

import os
import random
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta


def _env_float(name: str, default: float) -> float:
    """
    Lee un número de una variable de entorno con valor por defecto.

    Args:
        name (str): Nombre de la variable de entorno.
        default (float): Valor si la variable no existe o no es numérica.

    Returns:
        float: Valor configurado.
    """
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class McAssistantConfig:
    """
    Parámetros del Asistente MC. Se pueden ajustar por entorno, por ejemplo para una demo:
    `MC_ALERT_WINDOW_SECONDS=60` dispara la alerta tras 1 minuto en vez de 5.
    """

    window_seconds: float = 300.0  # Duración mínima de la caída para alertar (HU-18: 5 minutos)
    attention_threshold: float = (
        0.50  # Atención suavizada por debajo de este valor se considera baja
    )
    recovery_tolerance_seconds: float = 20.0  # Un repunte más corto no corta la racha
    signal_gap_seconds: float = 30.0  # Sin métricas por más tiempo, la racha se reinicia
    cooldown_seconds: float = 300.0  # Espera mínima entre alertas automáticas
    recovery_expire_seconds: float = 30.0  # Atención recuperada este tiempo vence la alerta activa
    break_grace_seconds: float = 60.0  # Tras una pausa no se alerta mientras el público regresa
    severe_attention: float = 0.30  # Por debajo, se priorizan pausas y reactivaciones fuertes

    @classmethod
    def from_env(cls) -> "McAssistantConfig":
        """
        Construye la configuración a partir de variables de entorno `MC_*`.

        Returns:
            McAssistantConfig: Configuración vigente.
        """
        base = cls()
        return cls(
            window_seconds=_env_float("MC_ALERT_WINDOW_SECONDS", base.window_seconds),
            attention_threshold=_env_float("MC_ATTENTION_THRESHOLD", base.attention_threshold),
            recovery_tolerance_seconds=_env_float(
                "MC_RECOVERY_TOLERANCE_SECONDS", base.recovery_tolerance_seconds
            ),
            signal_gap_seconds=_env_float("MC_SIGNAL_GAP_SECONDS", base.signal_gap_seconds),
            cooldown_seconds=_env_float("MC_ALERT_COOLDOWN_SECONDS", base.cooldown_seconds),
            recovery_expire_seconds=_env_float(
                "MC_RECOVERY_EXPIRE_SECONDS", base.recovery_expire_seconds
            ),
            break_grace_seconds=_env_float("MC_BREAK_GRACE_SECONDS", base.break_grace_seconds),
            severe_attention=_env_float("MC_SEVERE_ATTENTION", base.severe_attention),
        )


SMOOTHING_SAMPLES = 4


class InattentionTracker:
    """
    Sigue la racha de atención baja de una sesión (HU-18).

    La atención se suaviza con la media de las últimas 4 muestras (10 s). La racha empieza en la
    primera muestra baja y continúa aunque haya repuntes más cortos que la tolerancia. Si la cámara
    deja de enviar métricas más tiempo que `signal_gap_seconds`, la racha se reinicia.
    """

    def __init__(self, config: McAssistantConfig) -> None:
        """
        Inicializa el seguimiento sin muestras.

        Args:
            config (McAssistantConfig): Parámetros del asistente.
        """
        self.config = config
        self._recent: deque[float] = deque(maxlen=SMOOTHING_SAMPLES)
        self._low_values: list[float] = []
        self.low_since: datetime | None = None
        self.last_low_at: datetime | None = None
        self.high_since: datetime | None = None
        self.last_sample_at: datetime | None = None

    @property
    def smoothed_attention(self) -> float | None:
        """
        Atención suavizada actual.

        Returns:
            float | None: Media de las últimas muestras, o None si aún no hay muestras.
        """
        return sum(self._recent) / len(self._recent) if self._recent else None

    def reset(self) -> None:
        """Reinicia la racha de atención baja conservando la suavización."""
        self.low_since = None
        self.last_low_at = None
        self._low_values = []

    def add(self, recorded_at: datetime, attention: float) -> None:
        """
        Incorpora una muestra en orden cronológico.

        Args:
            recorded_at (datetime): Instante UTC de la métrica.
            attention (float): Atención promedio de la audiencia (0.0 a 1.0).
        """
        if self.last_sample_at is not None:
            if recorded_at <= self.last_sample_at:
                return
            if (recorded_at - self.last_sample_at).total_seconds() > self.config.signal_gap_seconds:
                self.reset()
                self._recent.clear()
                self.high_since = None
        self.last_sample_at = recorded_at
        self._recent.append(max(0.0, min(1.0, attention)))
        smoothed = self.smoothed_attention or 0.0

        if smoothed < self.config.attention_threshold:
            if self.low_since is None:
                self.low_since = recorded_at
            self.last_low_at = recorded_at
            self.high_since = None
            self._low_values.append(smoothed)
            return

        if self.high_since is None:
            self.high_since = recorded_at
        recovered_for = (recorded_at - self.high_since).total_seconds()
        if self.low_since is not None and recovered_for >= self.config.recovery_tolerance_seconds:
            self.reset()

    def low_duration_seconds(self) -> float:
        """
        Duración de la racha de atención baja vigente.

        Returns:
            float: Segundos entre la primera y la última muestra baja de la racha (0 sin racha).
        """
        if self.low_since is None or self.last_low_at is None:
            return 0.0
        return (self.last_low_at - self.low_since).total_seconds()

    def is_sustained(self) -> bool:
        """
        Indica si la atención lleva baja al menos la ventana configurada (regla HU-18).

        Returns:
            bool: True si corresponde emitir la alerta.
        """
        return self.low_duration_seconds() >= self.config.window_seconds

    def average_low_attention(self) -> float | None:
        """
        Atención media durante la racha baja.

        Returns:
            float | None: Promedio redondeado a 3 decimales, o None sin racha.
        """
        if not self._low_values:
            return None
        return round(sum(self._low_values) / len(self._low_values), 3)

    def recovered_seconds(self, now: datetime) -> float:
        """
        Tiempo que la atención lleva por encima del umbral.

        Args:
            now (datetime): Instante actual en UTC.

        Returns:
            float: Segundos desde que la atención volvió a subir (0 si sigue baja).
        """
        if self.high_since is None:
            return 0.0
        return max(0.0, (now - self.high_since).total_seconds())


@dataclass(frozen=True)
class DynamicOption:
    """Dinámica del catálogo reducida a lo necesario para elegirla."""

    id: str
    code: str
    dynamic_type: str
    modality: str
    intensity: int


def modality_matches(dynamic_modality: str, session_modality: str | None) -> bool:
    """
    Indica si una dinámica sirve para la modalidad de la experiencia.

    Args:
        dynamic_modality (str): `ANY`, `IN_PERSON` o `VIRTUAL`.
        session_modality (str | None): Modalidad de la experiencia (`IN_PERSON`, `VIRTUAL`, `HYBRID`).

    Returns:
        bool: True si la dinámica es aplicable. En eventos híbridos solo se usan dinámicas `ANY`.
    """
    if dynamic_modality == "ANY":
        return True
    return dynamic_modality == session_modality


def choose_dynamic(
    catalog: Sequence[DynamicOption],
    session_modality: str | None,
    attention: float | None,
    recent_codes: Sequence[str],
    config: McAssistantConfig,
    rng: random.Random | None = None,
) -> DynamicOption | None:
    """
    Elige la dinámica a proponer (HU-19).

    Con atención severa (por debajo de `severe_attention`) prioriza pausas y reactivaciones de
    intensidad alta; si no, prioriza preguntas e interacciones suaves. Evita repetir las dinámicas
    usadas recientemente en la sesión mientras haya alternativas.

    Args:
        catalog (Sequence[DynamicOption]): Dinámicas activas del catálogo.
        session_modality (str | None): Modalidad de la experiencia.
        attention (float | None): Atención media de la caída.
        recent_codes (Sequence[str]): Códigos ya propuestos en la sesión, del más antiguo al más reciente.
        config (McAssistantConfig): Parámetros del asistente.
        rng (random.Random | None): Generador inyectable para resultados repetibles.

    Returns:
        DynamicOption | None: Dinámica elegida, o None si el catálogo está vacío.
    """
    rng = rng or random.Random()
    candidates = [d for d in catalog if modality_matches(d.modality, session_modality)]
    if not candidates:
        return None

    fresh = [d for d in candidates if d.code not in recent_codes] or candidates
    severe = attention is not None and attention < config.severe_attention
    if severe:
        preferred = [d for d in fresh if d.intensity >= 2 and d.dynamic_type != "AUDIENCE_QUESTION"]
    else:
        preferred = [d for d in fresh if d.dynamic_type == "AUDIENCE_QUESTION" or d.intensity == 1]
    pool = preferred or fresh
    return rng.choice(sorted(pool, key=lambda d: d.code))


def break_window_end(break_ends_at: datetime | None, config: McAssistantConfig) -> datetime | None:
    """
    Calcula hasta cuándo se suspenden las alertas tras una pausa aplicada.

    Args:
        break_ends_at (datetime | None): Fin de la pausa.
        config (McAssistantConfig): Parámetros del asistente.

    Returns:
        datetime | None: Fin de la pausa más el margen de regreso, o None si no hay pausa.
    """
    if break_ends_at is None:
        return None
    return break_ends_at + timedelta(seconds=config.break_grace_seconds)
