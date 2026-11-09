"""Estimación etaria efímera del público en vivo con ventana deslizante en memoria (HU-16).

Privacidad: el fotograma solo se entrega al estimador dentro de `process_frame` y se libera al
terminar la llamada. El servicio conserva únicamente conteos por rango etario; no guarda imágenes,
no las persiste en PostgreSQL y no registra su contenido en logs.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.booking.service.booking_service import uuid_string
from app.live.dto.age_distribution_dto import AgeDistributionDTO, AgeGroupShareDTO
from app.live.entity.audience_metric import AgeGroupEnum
from app.live.entity.live_session import LiveSession

logger = logging.getLogger(__name__)

# Orden fijo en el que se informan los rangos al cliente.
AGE_GROUP_ORDER: tuple[AgeGroupEnum, ...] = (
    AgeGroupEnum.YOUTH,
    AgeGroupEnum.YOUNG_ADULT,
    AgeGroupEnum.ADULT,
    AgeGroupEnum.SENIOR,
)
_GROUP_INDEX: dict[AgeGroupEnum, int] = {group: index for index, group in enumerate(AGE_GROUP_ORDER)}

DEFAULT_WINDOW_SECONDS = 60
DEFAULT_MAX_SAMPLES_PER_SESSION = 600


class AgeEstimator(Protocol):
    """
    Contrato que debe cumplir cualquier modelo de estimación de edad (HU-16).

    Permite cambiar el modelo sin modificar la agregación: basta registrar otra implementación
    con `set_age_estimator`.
    """

    def estimate(self, frame: bytes) -> Sequence[AgeGroupEnum | str]:
        """
        Clasifica los rostros presentes en un fotograma codificado (JPEG/PNG) en memoria.

        Args:
            frame (bytes): Fotograma decodificado de Base64. No debe guardarse ni registrarse.

        Returns:
            Sequence[AgeGroupEnum | str]: Un rango etario por rostro detectado; vacío si no hay rostros.
        """
        ...


class AgeEstimationError(RuntimeError):
    """El estimador falló o devolvió un rango inválido; no incluye datos del fotograma."""


@dataclass(frozen=True, slots=True)
class _AgeSample:
    """Conteos de un fotograma ya procesado; nunca contiene la imagen."""

    monotonic_at: float
    recorded_at: datetime
    counts: tuple[int, ...]


def _utc_now() -> datetime:
    """
    Obtiene la fecha y hora actual en UTC.

    Returns:
        datetime: Marca de tiempo consciente de zona horaria UTC.
    """
    return datetime.now(timezone.utc)


def _session_key(session_id: str) -> str:
    """
    Normaliza el identificador de sesión para que ingesta y consulta usen la misma clave.

    Args:
        session_id (str): ID de la sesión en vivo, preferentemente UUID.

    Returns:
        str: UUID canónico en minúsculas o el texto recibido sin espacios si no es un UUID.

    Raises:
        ValueError: Si el identificador está vacío.
    """
    value = str(session_id or "").strip()
    if not value:
        raise ValueError("El ID de la sesión en vivo es obligatorio.")
    try:
        return str(UUID(value))
    except ValueError:
        return value


def _coerce_age_group(value: AgeGroupEnum | str) -> AgeGroupEnum:
    """
    Convierte la salida del estimador en un rango etario válido.

    Args:
        value (AgeGroupEnum | str): Rango devuelto por el modelo.

    Returns:
        AgeGroupEnum: Rango etario reconocido.

    Raises:
        ValueError: Si el valor no corresponde a YOUTH, YOUNG_ADULT, ADULT ni SENIOR.
    """
    return value if isinstance(value, AgeGroupEnum) else AgeGroupEnum(str(value))


def age_group_for_age(age: float) -> AgeGroupEnum:
    """
    Asigna una edad numérica estimada a su rango etario, para modelos que devuelven años.

    Usa los rangos documentados en `AgeGroupEnum`: menos de 18, 18 a 30, 31 a 50 y más de 50.

    Args:
        age (float): Edad estimada en años.

    Returns:
        AgeGroupEnum: Rango etario correspondiente.

    Raises:
        ValueError: Si la edad es negativa o no es un número finito.
    """
    value = float(age)
    if not math.isfinite(value) or value < 0:
        raise ValueError("La edad estimada debe ser un número finito no negativo.")
    if value < 18:
        return AgeGroupEnum.YOUTH
    if value < 31:
        return AgeGroupEnum.YOUNG_ADULT
    if value <= 50:
        return AgeGroupEnum.ADULT
    return AgeGroupEnum.SENIOR


class AgeDistributionService:
    """
    Agrega rangos etarios por sesión en una ventana deslizante en memoria RAM (HU-16).

    Cada fotograma aporta solo sus conteos por rango. Los porcentajes se calculan sobre los rostros
    clasificados dentro de la ventana; las muestras vencidas y las sesiones sin muestras se descartan.
    El estado vive en el proceso actual: con varios workers, cada uno mantiene su propia ventana.
    """

    def __init__(
        self,
        estimator: AgeEstimator | None = None,
        *,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        max_samples_per_session: int = DEFAULT_MAX_SAMPLES_PER_SESSION,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = _utc_now,
        estimator_factory: Callable[[], AgeEstimator | None] | None = None,
    ) -> None:
        """
        Inicializa el agregador sin abrir conexiones ni cargar modelos.

        Args:
            estimator (AgeEstimator | None): Modelo de edad fijado de antemano; None para resolverlo después.
            window_seconds (int): Duración de la ventana deslizante en segundos.
            max_samples_per_session (int): Límite de fotogramas retenidos por sesión para acotar memoria.
            clock (Callable[[], float]): Reloj monotónico usado para vencer muestras.
            wall_clock (Callable[[], datetime]): Reloj UTC usado para informar `updated_at`.
            estimator_factory (Callable[[], AgeEstimator | None] | None): Constructor perezoso que se
                intenta una sola vez en el primer uso si no hay estimador fijado; puede devolver None.

        Raises:
            ValueError: Si la ventana o el límite de muestras son menores que 1.
            TypeError: Si el estimador no implementa `estimate`.
        """
        if int(window_seconds) < 1:
            raise ValueError("La ventana debe durar al menos 1 segundo.")
        if int(max_samples_per_session) < 1:
            raise ValueError("El límite de muestras por sesión debe ser al menos 1.")
        self._window_seconds = int(window_seconds)
        self._max_samples = int(max_samples_per_session)
        self._clock = clock
        self._wall_clock = wall_clock
        self._sessions: dict[str, deque[_AgeSample]] = {}
        self._lock = threading.Lock()
        self._factory_lock = threading.Lock()
        self._estimator: AgeEstimator | None = None
        self._estimator_factory: Callable[[], AgeEstimator | None] | None = None
        self.set_estimator(estimator)
        if estimator is None:
            self._estimator_factory = estimator_factory

    @property
    def window_seconds(self) -> int:
        """
        Duración configurada de la ventana deslizante.

        Returns:
            int: Segundos de la ventana.
        """
        return self._window_seconds

    @property
    def estimator_configured(self) -> bool:
        """
        Indica si hay un modelo de edad registrado, intentando antes la construcción perezosa.

        Returns:
            bool: True si existe un estimador; False en caso contrario.
        """
        return self._resolve_estimator() is not None

    def set_estimator(self, estimator: AgeEstimator | None) -> None:
        """
        Fija o retira el modelo de estimación de edad sin perder las ventanas actuales.

        Un valor fijado explícitamente, incluso None, tiene prioridad y desactiva la construcción perezosa.

        Args:
            estimator (AgeEstimator | None): Implementación con método `estimate(frame)`, o None.

        Raises:
            TypeError: Si el objeto no expone un método `estimate` invocable.
        """
        if estimator is not None and not callable(getattr(estimator, "estimate", None)):
            raise TypeError("El estimador de edad debe implementar estimate(frame: bytes).")
        with self._lock:
            self._estimator = estimator
            self._estimator_factory = None

    def process_frame(self, session_id: str, frame: bytes) -> AgeDistributionDTO:
        """
        Clasifica un fotograma en RAM, guarda solo sus conteos y devuelve la distribución vigente.

        El fotograma se entrega al estimador y se libera al terminar; no se almacena ni se registra.
        Sin estimador registrado no se inventan datos: se devuelve la ventana actual sin cambios.

        Args:
            session_id (str): ID de la sesión en vivo.
            frame (bytes): Fotograma JPEG/PNG ya decodificado de Base64.

        Returns:
            AgeDistributionDTO: Distribución de la ventana después de procesar el fotograma.

        Raises:
            ValueError: Si el ID de la sesión está vacío.
            AgeEstimationError: Si el estimador falla o devuelve un rango inválido.
        """
        _session_key(session_id)
        estimator = self._resolve_estimator()
        if estimator is None:
            del frame
            return self.latest(session_id)
        try:
            groups = [_coerce_age_group(value) for value in estimator.estimate(frame)]
        except Exception:
            groups = None
        finally:
            del frame
        if groups is None:
            # Se lanza fuera del except para no encadenar el error original ni su contexto.
            raise AgeEstimationError("El estimador de edad no pudo procesar el fotograma.")
        return self.record_groups(session_id, groups)

    def record_groups(self, session_id: str, groups: Sequence[AgeGroupEnum | str]) -> AgeDistributionDTO:
        """
        Registra los rangos etarios de un fotograma ya clasificado en la ventana de su sesión.

        Args:
            session_id (str): ID de la sesión en vivo.
            groups (Sequence[AgeGroupEnum | str]): Un rango por rostro; vacío si no hubo rostros.

        Returns:
            AgeDistributionDTO: Distribución de la ventana incluyendo esta muestra.

        Raises:
            ValueError: Si el ID está vacío o algún rango no es válido.
        """
        key = _session_key(session_id)
        self._resolve_estimator()
        counts = [0] * len(AGE_GROUP_ORDER)
        for value in groups:
            counts[_GROUP_INDEX[_coerce_age_group(value)]] += 1
        sample = _AgeSample(monotonic_at=self._clock(), recorded_at=self._wall_clock(), counts=tuple(counts))
        with self._lock:
            self._prune_expired_locked(sample.monotonic_at)
            samples = self._sessions.setdefault(key, deque(maxlen=self._max_samples))
            samples.append(sample)
            return self._snapshot_locked(key)

    def latest(self, session_id: str) -> AgeDistributionDTO:
        """
        Consulta la última distribución porcentual de una sesión sin modificarla.

        Args:
            session_id (str): ID de la sesión en vivo.

        Returns:
            AgeDistributionDTO: Distribución vigente; con ceros y `updated_at` null si la ventana está vacía.

        Raises:
            ValueError: Si el ID de la sesión está vacío.
        """
        key = _session_key(session_id)
        self._resolve_estimator()
        with self._lock:
            self._prune_expired_locked(self._clock())
            return self._snapshot_locked(key)

    def clear(self, session_id: str) -> None:
        """
        Descarta la ventana de una sesión, por ejemplo al finalizar la transmisión.

        Args:
            session_id (str): ID de la sesión en vivo.

        Raises:
            ValueError: Si el ID de la sesión está vacío.
        """
        key = _session_key(session_id)
        with self._lock:
            self._sessions.pop(key, None)

    def distribution_for_host(self, db: Session, session_id: str, host_id: str) -> AgeDistributionDTO:
        """
        Devuelve la distribución solo al anfitrión propietario de la sesión en vivo.

        Args:
            db (Session): Sesión de base de datos de la petición.
            session_id (str): ID (UUID) de la sesión en vivo.
            host_id (str): ID del usuario autenticado.

        Returns:
            AgeDistributionDTO: Última distribución etaria de la sesión.

        Raises:
            HTTPException (422): Si el ID no es un UUID válido.
            HTTPException (404): Si la sesión en vivo no existe.
            HTTPException (403): Si la sesión pertenece a otro anfitrión.
        """
        canonical_id = uuid_string(session_id)
        live_session = db.get(LiveSession, canonical_id)
        if not live_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesión en vivo no encontrada")
        if str(live_session.host_id) != str(host_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No administras esta sesión en vivo")
        return self.latest(canonical_id)

    def _resolve_estimator(self) -> AgeEstimator | None:
        """
        Devuelve el estimador vigente y, si no hay uno fijado, intenta construirlo una sola vez.

        Un fallo del constructor no interrumpe la ingesta: el servicio sigue sin modelo y lo informa
        con `estimator_configured: false`. Para reintentar tras corregir la configuración, reinicia la API.

        Returns:
            AgeEstimator | None: Estimador registrado, o None si no existe ninguno disponible.
        """
        if self._estimator is not None or self._estimator_factory is None:
            return self._estimator
        with self._factory_lock:
            factory = self._estimator_factory
            if self._estimator is not None or factory is None:
                return self._estimator
            try:
                estimator = factory()
            except Exception:
                estimator = None
                logger.warning("No se pudo construir el estimador de edad; HU-16 continúa sin modelo.")
            if estimator is not None and not callable(getattr(estimator, "estimate", None)):
                estimator = None
                logger.warning("El estimador de edad construido no implementa estimate(frame); se descarta.")
            with self._lock:
                # Un set_estimator concurrente tiene prioridad sobre la construcción perezosa.
                if self._estimator_factory is factory:
                    self._estimator = estimator
                    self._estimator_factory = None
            return self._estimator

    def _prune_expired_locked(self, now: float) -> None:
        """
        Elimina muestras fuera de la ventana y sesiones sin muestras; requiere el candado tomado.

        Args:
            now (float): Instante actual del reloj monotónico.
        """
        limit = now - self._window_seconds
        for key in list(self._sessions):
            samples = self._sessions[key]
            while samples and samples[0].monotonic_at <= limit:
                samples.popleft()
            if not samples:
                del self._sessions[key]

    def _snapshot_locked(self, key: str) -> AgeDistributionDTO:
        """
        Calcula porcentajes y rango dominante de la ventana; requiere el candado tomado.

        Args:
            key (str): Clave normalizada de la sesión.

        Returns:
            AgeDistributionDTO: Distribución agregada de la ventana actual.
        """
        samples = self._sessions.get(key) or ()
        totals = [sum(sample.counts[index] for sample in samples) for index in range(len(AGE_GROUP_ORDER))]
        detections = sum(totals)
        distribution = [
            AgeGroupShareDTO(
                age_group=group,
                count=count,
                percentage=round(count * 100 / detections, 1) if detections else 0.0,
            )
            for group, count in zip(AGE_GROUP_ORDER, totals)
        ]
        dominant = None
        if detections:
            # En empate gana el primer rango del orden fijo, para que la respuesta sea estable.
            dominant = AGE_GROUP_ORDER[max(range(len(totals)), key=totals.__getitem__)]
        return AgeDistributionDTO(
            session_id=key,
            window_seconds=self._window_seconds,
            sample_count=len(samples),
            detections_count=detections,
            distribution=distribution,
            dominant_age_group=dominant,
            updated_at=samples[-1].recorded_at if samples else None,
            estimator_configured=self._estimator is not None,
        )


def _build_default_estimator() -> AgeEstimator | None:
    """
    Construye el estimador OpenCV a partir de las rutas de modelos configuradas en el entorno.

    Returns:
        AgeEstimator | None: Estimador listo, o None si faltan los modelos o no pueden cargarse.
    """
    from app.live.service.opencv_age_estimator import build_age_estimator_from_settings

    return build_age_estimator_from_settings()


# Instancia compartida por la ingesta y el endpoint de consulta dentro del proceso.
# Si nadie fija un estimador con set_age_estimator, se intenta construir el de OpenCV en el primer uso.
age_distribution_service = AgeDistributionService(estimator_factory=_build_default_estimator)


def get_age_distribution_service() -> AgeDistributionService:
    """
    Dependencia de FastAPI que entrega el agregador compartido del proceso.

    Returns:
        AgeDistributionService: Instancia única usada por la ingesta y la consulta.
    """
    return age_distribution_service


def set_age_estimator(estimator: AgeEstimator | None) -> None:
    """
    Fija el modelo de edad del proceso y reemplaza al estimador OpenCV construido por defecto (HU-16).

    Solo es necesario para usar otro modelo; con las rutas de OpenCV configuradas no hace falta llamarla.

    Args:
        estimator (AgeEstimator | None): Implementación del contrato `AgeEstimator`, o None para retirarla.

    Raises:
        TypeError: Si el objeto no implementa `estimate(frame: bytes)`.
    """
    age_distribution_service.set_estimator(estimator)
