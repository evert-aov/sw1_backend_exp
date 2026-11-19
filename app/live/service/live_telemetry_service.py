"""
Servicio de telemetría agregada en vivo para la consola del anfitrión (CU-09 / HU-17).

Mantiene un canal por sesión en vivo que, cada 2.5 s, recoge las métricas agregadas producidas por
el pipeline de visión (HU-13 a HU-16), calcula el semáforo de energía suavizado y emite la misma
instantánea a todos los clientes suscritos (consola web, tablet y app móvil).

Fuentes de métricas:
- Publicación en proceso: el canal de ingesta llama a `LiveTelemetryHub.publish(session_id, metrics)`.
- Base de datos: las métricas persistidas en `audience_metrics` se leen en cada ciclo, de modo que la
  consola funciona aunque la ingesta ocurra en otro proceso.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from app.core.database import SessionLocal
from app.live.dto.live_dto import LiveMetricsDTO
from app.live.dto.live_telemetry_dto import (
    EnergyTrafficLightEnum,
    LiveTelemetrySnapshotDTO,
    PulsePointDTO,
    SignalStatusEnum,
)
from app.live.entity.audience_metric import AgeGroupEnum
from app.live.repository.live_telemetry_repository import LiveTelemetryRepository
from app.live.service.energy_indicator import (
    SMOOTHING_WINDOW,
    compute_energy_score,
    compute_trend,
    resolve_traffic_light,
    smooth_energy,
)

logger = logging.getLogger(__name__)

# Intervalo de emisión sincronizada definido por HU-17
BROADCAST_INTERVAL_SECONDS = 2.5

# Puntos conservados para la gráfica de pulso (24 x 2.5 s = 60 s)
PULSE_WINDOW_SIZE = 24

# Una métrica es "en vivo" si llegó dentro de 3 intervalos; "desactualizada" hasta 30 s
LIVE_SIGNAL_MAX_AGE_SECONDS = BROADCAST_INTERVAL_SECONDS * 3
STALE_SIGNAL_MAX_AGE_SECONDS = 30.0

# Al abrir un canal solo se cargan métricas recientes para no mostrar datos de otra transmisión
INITIAL_LOOKBACK_SECONDS = PULSE_WINDOW_SIZE * BROADCAST_INTERVAL_SECONDS * 2


def utc_now() -> datetime:
    """
    Devuelve el instante actual en UTC con zona horaria.

    Returns:
        datetime: Fecha y hora actual en UTC.
    """
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """
    Normaliza una fecha a UTC con zona horaria; las fechas sin zona se interpretan como UTC.

    Args:
        value (datetime): Fecha con o sin zona horaria (PostgreSQL guarda `recorded_at` sin zona).

    Returns:
        datetime: Fecha equivalente en UTC con zona horaria.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class MetricSample:
    """Métrica agregada mínima que necesita la HU-17, independiente de su origen (DTO u ORM)."""

    recorded_at: datetime
    attention_score: float
    joy_score: float
    detected_faces_count: int
    dominant_age_group: AgeGroupEnum | None

    @classmethod
    def from_metric(cls, metric: Any) -> "MetricSample":
        """
        Construye una muestra desde un `LiveMetricsDTO` o una entidad `AudienceMetric`.

        Args:
            metric (Any): Objeto con los atributos de una métrica agregada de audiencia.

        Returns:
            MetricSample: Muestra normalizada con fecha en UTC.
        """
        age = metric.dominant_age_group
        if age is not None and not isinstance(age, AgeGroupEnum):
            age = AgeGroupEnum(age)
        return cls(
            recorded_at=as_utc(metric.recorded_at),
            attention_score=float(metric.attention_score or 0.0),
            joy_score=float(metric.joy_score or 0.0),
            detected_faces_count=int(metric.detected_faces_count or 0),
            dominant_age_group=age,
        )


class MetricsSource(Protocol):
    """Contrato de una fuente de métricas persistidas para un canal de telemetría."""

    def __call__(self, session_id: str, after: datetime, limit: int) -> list[MetricSample]:
        """
        Devuelve las métricas de la sesión posteriores a `after`, en orden cronológico.

        Args:
            session_id (str): UUID de la sesión en vivo.
            after (datetime): Instante exclusivo en UTC desde el cual buscar.
            limit (int): Cantidad máxima de métricas a devolver.

        Returns:
            list[MetricSample]: Métricas nuevas de la sesión.
        """
        ...


def database_metrics_source(session_id: str, after: datetime, limit: int) -> list[MetricSample]:
    """
    Fuente de métricas por defecto: lee `audience_metrics` en PostgreSQL con una sesión breve.

    Args:
        session_id (str): UUID de la sesión en vivo.
        after (datetime): Instante exclusivo en UTC desde el cual buscar.
        limit (int): Cantidad máxima de métricas a devolver.

    Returns:
        list[MetricSample]: Métricas nuevas de la sesión en orden cronológico.
    """
    naive_after = as_utc(after).replace(tzinfo=None)
    with SessionLocal() as db:
        rows = LiveTelemetryRepository(db).get_metrics_after(session_id, naive_after, limit)
        return [MetricSample.from_metric(row) for row in rows]


class SessionTelemetryState:
    """
    Estado en memoria de la telemetría de una sesión: muestras recientes, semáforo y pulso.

    Solo guarda números agregados; nunca fotogramas ni datos personales (GDPR).
    """

    def __init__(self, session_id: str) -> None:
        """
        Inicializa el estado vacío de una sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.
        """
        self.session_id = session_id
        self.raw_energy: deque[float] = deque(maxlen=SMOOTHING_WINDOW)
        self.pulse: deque[PulsePointDTO] = deque(maxlen=PULSE_WINDOW_SIZE)
        self.traffic_light: EnergyTrafficLightEnum | None = None
        self.latest: MetricSample | None = None
        self.fresh: list[MetricSample] = []  # Muestras nuevas aún no entregadas a los oyentes

    @property
    def last_recorded_at(self) -> datetime | None:
        """
        Instante de la última métrica incorporada.

        Returns:
            datetime | None: Fecha UTC de la última muestra, o None si aún no hay muestras.
        """
        return self.latest.recorded_at if self.latest else None

    def ingest(self, sample: MetricSample) -> bool:
        """
        Incorpora una muestra si es más reciente que la última, actualizando semáforo y pulso.

        Args:
            sample (MetricSample): Métrica agregada a incorporar.

        Returns:
            bool: True si la muestra se incorporó; False si era repetida o anterior.
        """
        if self.latest is not None and sample.recorded_at <= self.latest.recorded_at:
            return False

        self.raw_energy.append(compute_energy_score(sample.attention_score, sample.joy_score))
        smoothed = smooth_energy(self.raw_energy)
        self.traffic_light = resolve_traffic_light(smoothed, self.traffic_light)
        self.pulse.append(
            PulsePointDTO(
                recorded_at=sample.recorded_at,
                energy_score=smoothed,
                traffic_light=self.traffic_light,
            )
        )
        self.latest = sample
        self.fresh.append(sample)
        return True

    def signal_status(self, now: datetime) -> SignalStatusEnum:
        """
        Calcula el estado de la señal según la antigüedad de la última métrica.

        Args:
            now (datetime): Instante actual en UTC.

        Returns:
            SignalStatusEnum: LIVE, STALE o NO_SIGNAL.
        """
        if self.latest is None:
            return SignalStatusEnum.NO_SIGNAL
        age_seconds = (now - self.latest.recorded_at).total_seconds()
        if age_seconds <= LIVE_SIGNAL_MAX_AGE_SECONDS:
            return SignalStatusEnum.LIVE
        if age_seconds <= STALE_SIGNAL_MAX_AGE_SECONDS:
            return SignalStatusEnum.STALE
        return SignalStatusEnum.NO_SIGNAL

    def snapshot(self, now: datetime) -> LiveTelemetrySnapshotDTO:
        """
        Construye la instantánea de telemetría que se emite a los clientes.

        Args:
            now (datetime): Instante de emisión en UTC.

        Returns:
            LiveTelemetrySnapshotDTO: Semáforo, tendencia, últimos valores y puntos de pulso.
        """
        latest = self.latest
        pulse = list(self.pulse)
        return LiveTelemetrySnapshotDTO(
            session_id=self.session_id,
            emitted_at=now,
            interval_seconds=BROADCAST_INTERVAL_SECONDS,
            signal_status=self.signal_status(now),
            energy_score=pulse[-1].energy_score if pulse else None,
            traffic_light=self.traffic_light,
            trend=compute_trend([point.energy_score for point in pulse]),
            attention_score=round(latest.attention_score, 3) if latest else None,
            joy_score=round(latest.joy_score, 3) if latest else None,
            detected_faces_count=latest.detected_faces_count if latest else None,
            dominant_age_group=latest.dominant_age_group if latest else None,
            last_metric_at=latest.recorded_at if latest else None,
            pulse=pulse,
        )


class TelemetrySubscriber(Protocol):
    """Contrato mínimo de un cliente suscrito (compatible con `fastapi.WebSocket`)."""

    async def send_text(self, data: str) -> None:
        """
        Envía un mensaje de texto al cliente.

        Args:
            data (str): Mensaje JSON serializado.
        """
        ...


class TelemetryListener(Protocol):
    """
    Módulo que reacciona a la telemetría de cada sesión (por ejemplo, el Asistente MC de HU-18).

    Los mensajes que devuelve se envían a los clientes del mismo canal WebSocket.
    """

    async def on_subscribe(self, session_id: str) -> list[str]:
        """
        Mensajes iniciales para un cliente recién conectado.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            list[str]: Mensajes JSON serializados.
        """
        ...

    async def on_tick(
        self, session_id: str, samples: list[MetricSample], now: datetime
    ) -> list[str]:
        """
        Procesa las muestras nuevas de un ciclo de emisión.

        Args:
            session_id (str): UUID de la sesión en vivo.
            samples (list[MetricSample]): Muestras nuevas en orden cronológico.
            now (datetime): Instante del ciclo en UTC.

        Returns:
            list[str]: Mensajes JSON serializados a emitir a todos los clientes.
        """
        ...

    def on_release(self, session_id: str) -> None:
        """
        Libera el estado del oyente cuando el canal de la sesión se detiene.

        Args:
            session_id (str): UUID de la sesión en vivo.
        """
        ...


class LiveTelemetryHub:
    """
    Orquestador de canales de telemetría por sesión con emisión sincronizada cada 2.5 s (HU-17).

    Cada sesión con al menos un suscriptor tiene una tarea periódica que actualiza el estado desde la
    fuente de métricas y emite la misma instantánea a todos sus clientes. La tarea se detiene al
    desconectarse el último cliente.
    """

    def __init__(
        self,
        metrics_source: MetricsSource = database_metrics_source,
        interval_seconds: float = BROADCAST_INTERVAL_SECONDS,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """
        Inicializa el orquestador.

        Args:
            metrics_source (MetricsSource): Función que entrega métricas persistidas nuevas.
            interval_seconds (float): Intervalo de emisión sincronizada en segundos.
            clock (Callable[[], datetime]): Reloj UTC inyectable para pruebas.
        """
        self._metrics_source = metrics_source
        self._interval = interval_seconds
        self._clock = clock
        self._states: dict[str, SessionTelemetryState] = {}
        self._subscribers: dict[str, set[TelemetrySubscriber]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._listeners: list[TelemetryListener] = []
        self._retained_until: dict[str, datetime] = {}

    def _state_for(self, session_id: str) -> SessionTelemetryState:
        """
        Obtiene o crea el estado en memoria de una sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            SessionTelemetryState: Estado de telemetría de la sesión.
        """
        if session_id not in self._states:
            self._states[session_id] = SessionTelemetryState(session_id)
        return self._states[session_id]

    def subscriber_count(self, session_id: str) -> int:
        """
        Cuenta los clientes suscritos a una sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            int: Número de clientes conectados.
        """
        return len(self._subscribers.get(session_id, ()))

    def add_listener(self, listener: TelemetryListener) -> None:
        """
        Registra un módulo que reacciona a cada ciclo de telemetría.

        Args:
            listener (TelemetryListener): Oyente a registrar (se ignora si ya estaba registrado).
        """
        if listener not in self._listeners:
            self._listeners.append(listener)

    def is_active(self, session_id: str) -> bool:
        """
        Indica si el canal de la sesión debe seguir funcionando.

        Un canal está activo si tiene clientes conectados o si fue retenido (por ejemplo, porque un
        celular vinculado espera notificaciones push aunque no tenga el WebSocket abierto).

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            bool: True si hay clientes o una retención vigente.
        """
        if self.subscriber_count(session_id) > 0:
            return True
        until = self._retained_until.get(session_id)
        return until is not None and until > self._clock()

    def retain(self, session_id: str, until: datetime) -> None:
        """
        Mantiene el canal de la sesión activo sin clientes hasta la fecha indicada.

        Args:
            session_id (str): UUID de la sesión en vivo.
            until (datetime): Fecha UTC hasta la que se retiene el canal.
        """
        current = self._retained_until.get(session_id)
        self._retained_until[session_id] = until if current is None or until > current else current
        self._state_for(session_id)
        self._ensure_loop(session_id)

    def _ensure_loop(self, session_id: str) -> None:
        """
        Inicia el bucle de emisión de la sesión si no está corriendo.

        Args:
            session_id (str): UUID de la sesión en vivo.
        """
        task = self._tasks.get(session_id)
        if task is None or task.done():
            self._tasks[session_id] = asyncio.create_task(self._broadcast_loop(session_id))

    async def send_event(self, session_id: str, payload: str) -> None:
        """
        Emite un mensaje adicional (por ejemplo una alerta MC) a todos los clientes de la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.
            payload (str): Mensaje JSON serializado.
        """
        for subscriber in list(self._subscribers.get(session_id, ())):
            await self._send(session_id, subscriber, payload)

    def _release(self, session_id: str) -> None:
        """
        Libera el estado de una sesión que ya no está activa y avisa a los oyentes.

        Args:
            session_id (str): UUID de la sesión en vivo.
        """
        self._states.pop(session_id, None)
        self._retained_until.pop(session_id, None)
        for listener in self._listeners:
            try:
                listener.on_release(session_id)
            except Exception as exc:
                logger.warning("Oyente falló al liberar la sesión %s: %s", session_id, exc)

    def publish(self, session_id: str, metrics: LiveMetricsDTO) -> None:
        """
        Punto de integración para el pipeline de visión: registra una métrica recién calculada.

        La métrica se refleja en la siguiente emisión sincronizada (como máximo 2.5 s después).
        Si la misma métrica también se persiste en BD, no se duplica porque se descarta por fecha.
        Si ninguna consola observa la sesión se ignora: al abrirse una, el estado se carga desde BD.

        Args:
            session_id (str): UUID de la sesión en vivo.
            metrics (LiveMetricsDTO): Métrica agregada calculada por HU-15/HU-16.
        """
        state = self._states.get(session_id)
        if state is not None:
            state.ingest(MetricSample.from_metric(metrics))

    async def refresh(self, session_id: str) -> SessionTelemetryState:
        """
        Incorpora al estado de la sesión las métricas persistidas que aún no se procesaron.

        Si ninguna consola está suscrita, se usa un estado temporal que no se conserva en memoria.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            SessionTelemetryState: Estado actualizado de la sesión.
        """
        if self.is_active(session_id):
            state = self._state_for(session_id)
        else:
            state = self._states.get(session_id) or SessionTelemetryState(session_id)
        now = self._clock()
        after = state.last_recorded_at or (now - timedelta(seconds=INITIAL_LOOKBACK_SECONDS))
        try:
            samples = await asyncio.to_thread(
                self._metrics_source, session_id, after, PULSE_WINDOW_SIZE
            )
        except Exception as exc:  # La consola sigue emitiendo aunque la BD falle puntualmente
            logger.warning("No se pudieron leer métricas de la sesión %s: %s", session_id, exc)
            samples = []
        for sample in samples:
            state.ingest(sample)
        return state

    async def get_snapshot(self, session_id: str) -> LiveTelemetrySnapshotDTO:
        """
        Devuelve la instantánea vigente de una sesión, actualizada con las métricas persistidas.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            LiveTelemetrySnapshotDTO: Instantánea de telemetría actual.
        """
        state = await self.refresh(session_id)
        return state.snapshot(self._clock())

    async def subscribe(self, session_id: str, subscriber: TelemetrySubscriber) -> None:
        """
        Suscribe un cliente, le envía de inmediato la instantánea vigente e inicia la emisión periódica.

        Args:
            session_id (str): UUID de la sesión en vivo.
            subscriber (TelemetrySubscriber): Cliente WebSocket ya aceptado.
        """
        self._subscribers.setdefault(session_id, set()).add(subscriber)
        snapshot = await self.get_snapshot(session_id)
        await self._send(session_id, subscriber, snapshot.model_dump_json())
        for listener in self._listeners:
            try:
                for payload in await listener.on_subscribe(session_id):
                    await self._send(session_id, subscriber, payload)
            except Exception as exc:
                logger.warning(
                    "Oyente falló al suscribir un cliente a la sesión %s: %s", session_id, exc
                )

        self._ensure_loop(session_id)
        logger.info(
            "Consola suscrita a la sesión %s (%d clientes)",
            session_id,
            self.subscriber_count(session_id),
        )

    async def unsubscribe(self, session_id: str, subscriber: TelemetrySubscriber) -> None:
        """
        Elimina un cliente y, si era el último, detiene la emisión y libera el estado de la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.
            subscriber (TelemetrySubscriber): Cliente que se desconecta.
        """
        subscribers = self._subscribers.get(session_id)
        if subscribers is None:
            return
        subscribers.discard(subscriber)
        if subscribers:
            return

        del self._subscribers[session_id]
        if self.is_active(session_id):
            return  # Sigue retenida por un dispositivo vinculado
        self._release(session_id)
        task = self._tasks.pop(session_id, None)
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        logger.info("Emisión de telemetría detenida para la sesión %s", session_id)

    async def broadcast(self, session_id: str) -> LiveTelemetrySnapshotDTO:
        """
        Actualiza el estado y emite la misma instantánea a todos los clientes de la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            LiveTelemetrySnapshotDTO: Instantánea emitida.
        """
        state = await self.refresh(session_id)
        now = self._clock()
        snapshot = state.snapshot(now)
        await self.send_event(session_id, snapshot.model_dump_json())

        fresh, state.fresh = state.fresh, []
        for listener in self._listeners:
            try:
                events = await listener.on_tick(session_id, fresh, now)
            except Exception as exc:
                logger.warning("Oyente falló en la sesión %s: %s", session_id, exc)
                continue
            for payload in events:
                await self.send_event(session_id, payload)
        return snapshot

    async def _send(self, session_id: str, subscriber: TelemetrySubscriber, payload: str) -> None:
        """
        Envía un mensaje a un cliente y lo da de baja si la conexión ya no responde.

        Args:
            session_id (str): UUID de la sesión en vivo.
            subscriber (TelemetrySubscriber): Cliente destinatario.
            payload (str): Mensaje JSON serializado.
        """
        try:
            await subscriber.send_text(payload)
        except Exception:
            await self.unsubscribe(session_id, subscriber)

    async def _broadcast_loop(self, session_id: str) -> None:
        """
        Bucle de emisión sincronizada: cada intervalo emite a todos los clientes de la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.
        """
        try:
            while self.is_active(session_id):
                await asyncio.sleep(self._interval)
                await self.broadcast(session_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Fallo en la emisión de telemetría de la sesión %s: %s", session_id, exc)
        if not self.is_active(session_id) and self._tasks.get(session_id) is asyncio.current_task():
            self._tasks.pop(session_id, None)
            self._release(session_id)


# Instancia compartida por el proceso de la API
live_telemetry_hub = LiveTelemetryHub()


def get_live_telemetry_hub() -> LiveTelemetryHub:
    """
    Dependencia de FastAPI que entrega el orquestador de telemetría del proceso.

    Returns:
        LiveTelemetryHub: Instancia compartida del orquestador.
    """
    return live_telemetry_hub
