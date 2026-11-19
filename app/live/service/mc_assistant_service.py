"""
Asistente de Maestro de Ceremonias en vivo (CU-11 / HU-18, HU-19).

Se registra como oyente del `LiveTelemetryHub` (HU-17): en cada ciclo de 2.5 s recibe las métricas
nuevas, detecta la atención baja sostenida (5 minutos por defecto) y emite una alerta con una
dinámica sugerida por el mismo WebSocket de la consola. Si hay celulares vinculados, también envía
una notificación push con Firebase.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.live.dto.mc_assistant_dto import (
    McAlertDTO,
    McAlertEventDTO,
    McDynamicDTO,
    PushDeviceRegisteredDTO,
)
from app.live.entity.live_suggestion import LiveSuggestion, SuggestionTypeEnum
from app.live.entity.mc_alert import McAlert, McAlertStatusEnum, McAlertTriggerEnum
from app.live.entity.mc_dynamic import McDynamic, McDynamicTypeEnum
from app.live.entity.monitor_push_device import MonitorPushDevice
from app.live.repository.mc_assistant_repository import McAssistantRepository
from app.live.service.live_telemetry_service import (
    LiveTelemetryHub,
    MetricSample,
    as_utc,
    database_metrics_source,
    live_telemetry_hub,
    utc_now,
)
from app.live.service.mc_alert_engine import (
    DynamicOption,
    InattentionTracker,
    McAssistantConfig,
    break_window_end,
    choose_dynamic,
)
from app.live.service.mc_dynamics_seed import seed_mc_dynamics
from app.live.service.push_notification_service import PushMessage, PushNotificationService

logger = logging.getLogger(__name__)

BREAK_TYPES = frozenset({McDynamicTypeEnum.ACTIVE_BREAK, McDynamicTypeEnum.SHORT_BREAK})

PUSH_TITLES = {
    "es": "La atención del público está bajando",
    "en": "Audience attention is dropping",
}


def naive_utc(value: datetime) -> datetime:
    """
    Convierte una fecha a UTC sin zona horaria, formato de las columnas de la BD.

    Args:
        value (datetime): Fecha con o sin zona horaria.

    Returns:
        datetime: Fecha UTC sin zona.
    """
    return as_utc(value).replace(tzinfo=None)


def alert_to_dto(alert: McAlert, dynamic: McDynamic | None) -> McAlertDTO:
    """
    Convierte una entidad de alerta y su dinámica en el DTO público.

    Args:
        alert (McAlert): Alerta persistida.
        dynamic (McDynamic | None): Dinámica propuesta.

    Returns:
        McAlertDTO: Alerta con fechas en UTC con zona horaria.
    """
    return McAlertDTO(
        id=str(alert.id),
        session_id=str(alert.live_session_id),
        trigger=McAlertTriggerEnum(alert.trigger),
        status=McAlertStatusEnum(alert.status),
        average_attention=alert.average_attention,
        low_attention_seconds=int(alert.low_attention_seconds or 0),
        created_at=as_utc(alert.created_at),
        resolved_at=as_utc(alert.resolved_at) if alert.resolved_at else None,
        break_ends_at=as_utc(alert.break_ends_at) if alert.break_ends_at else None,
        suggestion_id=str(alert.suggestion_id) if alert.suggestion_id else None,
        dynamic=McDynamicDTO.model_validate(dynamic) if dynamic else None,
    )


def suggestion_type_for(dynamic: McDynamic) -> SuggestionTypeEnum:
    """
    Traduce el tipo de dinámica al tipo de sugerencia compartido de `live_suggestions`.

    Args:
        dynamic (McDynamic): Dinámica propuesta.

    Returns:
        SuggestionTypeEnum: BREAK para descansos cortos; MC_DYNAMIC en otro caso.
    """
    return (
        SuggestionTypeEnum.BREAK
        if dynamic.dynamic_type == McDynamicTypeEnum.SHORT_BREAK
        else SuggestionTypeEnum.MC_DYNAMIC
    )


@dataclass(frozen=True)
class SessionContext:
    """Estado persistido necesario para retomar el asistente de una sesión."""

    active_alert: McAlertDTO | None
    latest_break_end: datetime | None


class McAssistantStore:
    """Operaciones de base de datos del Asistente MC, cada una en su propia transacción corta."""

    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
        config: McAssistantConfig | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """
        Inicializa el almacén.

        Args:
            session_factory (Callable[[], Session]): Fábrica de sesiones de SQLAlchemy.
            config (McAssistantConfig | None): Parámetros del asistente.
            rng (random.Random | None): Generador para elegir dinámicas.
        """
        self._session_factory = session_factory
        self._config = config or McAssistantConfig.from_env()
        self._rng = rng or random.Random()

    def load_history(self, session_id: str, since: datetime) -> list[MetricSample]:
        """
        Lee las métricas recientes de la sesión para reconstruir la racha de atención.

        Args:
            session_id (str): UUID de la sesión en vivo.
            since (datetime): Instante UTC desde el cual leer.

        Returns:
            list[MetricSample]: Muestras en orden cronológico.
        """
        return database_metrics_source(session_id, since, 400)

    def load_context(self, session_id: str) -> SessionContext:
        """
        Lee la alerta activa y la última pausa de la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            SessionContext: Estado persistido de la sesión.
        """
        with self._session_factory() as db:
            repo = McAssistantRepository(db)
            alert = repo.get_active_alert(session_id)
            dto = alert_to_dto(alert, repo.get_dynamic(alert.dynamic_id)) if alert else None
            latest_break = repo.get_latest_break_end(session_id)
            return SessionContext(dto, as_utc(latest_break) if latest_break else None)

    def _pick_dynamic(
        self,
        repo: McAssistantRepository,
        session_id: str,
        attention: float | None,
        exclude: list[str],
    ) -> McDynamic | None:
        """
        Elige una dinámica del catálogo para la sesión, sembrando el catálogo si está vacío.

        Args:
            repo (McAssistantRepository): Repositorio en la transacción actual.
            session_id (str): UUID de la sesión en vivo.
            attention (float | None): Atención media de la caída.
            exclude (list[str]): Códigos a evitar.

        Returns:
            McDynamic | None: Dinámica elegida o None si no hay catálogo.
        """
        catalog = repo.list_active_dynamics()
        if not catalog:
            seed_mc_dynamics(repo.db)
            catalog = repo.list_active_dynamics()
        options = [
            DynamicOption(
                str(d.id),
                str(d.code),
                McDynamicTypeEnum(d.dynamic_type).value,
                getattr(d.modality, "value", str(d.modality)),
                int(d.intensity),
                tuple(d.category_names or ()),
            )
            for d in catalog
        ]
        chosen = choose_dynamic(
            options,
            repo.get_session_modality(session_id),
            attention,
            exclude + repo.recent_dynamic_codes(session_id, limit=8),
            self._config,
            self._rng,
            session_category=repo.get_session_category_name(session_id),
        )
        return repo.get_dynamic(chosen.id) if chosen else None

    def create_alert(
        self,
        session_id: str,
        trigger: McAlertTriggerEnum,
        average_attention: float | None,
        low_seconds: int,
        now: datetime,
    ) -> McAlertDTO:
        """
        Crea la alerta, elige la dinámica y registra la sugerencia en `live_suggestions`.

        Args:
            session_id (str): UUID de la sesión en vivo.
            trigger (McAlertTriggerEnum): Origen de la alerta.
            average_attention (float | None): Atención media de la caída.
            low_seconds (int): Segundos de atención baja sostenida.
            now (datetime): Instante de emisión en UTC.

        Returns:
            McAlertDTO: Alerta creada.
        """
        with self._session_factory() as db:
            repo = McAssistantRepository(db)
            dynamic = self._pick_dynamic(repo, session_id, average_attention, [])
            suggestion = None
            if dynamic is not None:
                suggestion = LiveSuggestion(
                    live_session_id=session_id,
                    suggestion_type=suggestion_type_for(dynamic),
                    suggestion_text=f"{dynamic.title_es}: {dynamic.instructions_es}",
                    applied_by_host=False,
                    created_at=naive_utc(now),
                )
                repo.add(suggestion)
                db.flush()
            alert = McAlert(
                live_session_id=session_id,
                dynamic_id=dynamic.id if dynamic else None,
                suggestion_id=suggestion.id if suggestion else None,
                trigger=trigger,
                status=McAlertStatusEnum.ACTIVE,
                average_attention=average_attention,
                low_attention_seconds=low_seconds,
                created_at=naive_utc(now),
            )
            repo.add(alert)
            db.commit()
            db.refresh(alert)
            return alert_to_dto(alert, dynamic)

    def resolve_alert(
        self, alert_id: str, new_status: McAlertStatusEnum, now: datetime
    ) -> McAlertDTO:
        """
        Cambia el estado de una alerta activa. Al aplicar un descanso, fija el fin de la pausa.

        Args:
            alert_id (str): UUID de la alerta.
            new_status (McAlertStatusEnum): APPLIED, DISMISSED o EXPIRED.
            now (datetime): Instante UTC de la respuesta.

        Returns:
            McAlertDTO: Alerta actualizada.

        Raises:
            HTTPException (404): Si la alerta no existe.
            HTTPException (409): Si la alerta ya no está activa.
        """
        with self._session_factory() as db:
            repo = McAssistantRepository(db)
            alert = repo.get_alert(alert_id)
            if alert is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada"
                )
            if alert.status != McAlertStatusEnum.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="La alerta ya fue atendida"
                )
            dynamic = repo.get_dynamic(alert.dynamic_id)
            alert.status = new_status
            alert.resolved_at = naive_utc(now)
            if new_status == McAlertStatusEnum.APPLIED:
                suggestion = repo.get_suggestion(alert.suggestion_id)
                if suggestion is not None:
                    setattr(suggestion, "applied_by_host", True)
                if dynamic is not None and dynamic.dynamic_type in BREAK_TYPES:
                    alert.break_ends_at = naive_utc(
                        now + timedelta(minutes=int(dynamic.duration_minutes))
                    )
            db.commit()
            db.refresh(alert)
            return alert_to_dto(alert, dynamic)

    def replace_dynamic(self, alert_id: str) -> McAlertDTO:
        """
        Propone otra dinámica para una alerta activa (botón "Otra idea").

        Args:
            alert_id (str): UUID de la alerta.

        Returns:
            McAlertDTO: Alerta con la nueva dinámica.

        Raises:
            HTTPException (404): Si la alerta no existe.
            HTTPException (409): Si la alerta ya no está activa.
        """
        with self._session_factory() as db:
            repo = McAssistantRepository(db)
            alert = repo.get_alert(alert_id)
            if alert is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada"
                )
            if alert.status != McAlertStatusEnum.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="La alerta ya fue atendida"
                )
            current = repo.get_dynamic(alert.dynamic_id)
            exclude = [str(current.code)] if current else []
            dynamic = (
                self._pick_dynamic(
                    repo, str(alert.live_session_id), alert.average_attention, exclude
                )
                or current
            )
            if dynamic is not None:
                alert.dynamic_id = dynamic.id
                suggestion = repo.get_suggestion(alert.suggestion_id)
                if suggestion is not None:
                    setattr(suggestion, "suggestion_type", suggestion_type_for(dynamic))
                    setattr(
                        suggestion,
                        "suggestion_text",
                        f"{dynamic.title_es}: {dynamic.instructions_es}",
                    )
            db.commit()
            db.refresh(alert)
            return alert_to_dto(alert, dynamic)

    def get_alert_session(self, alert_id: str) -> str | None:
        """
        Obtiene la sesión a la que pertenece una alerta.

        Args:
            alert_id (str): UUID de la alerta.

        Returns:
            str | None: UUID de la sesión o None si la alerta no existe.
        """
        with self._session_factory() as db:
            alert = McAssistantRepository(db).get_alert(alert_id)
            return str(alert.live_session_id) if alert else None

    def list_alerts(self, session_id: str, limit: int = 20) -> list[McAlertDTO]:
        """
        Lista el historial de alertas de la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.
            limit (int): Cantidad máxima de alertas.

        Returns:
            list[McAlertDTO]: Alertas de la más reciente a la más antigua.
        """
        with self._session_factory() as db:
            repo = McAssistantRepository(db)
            return [
                alert_to_dto(a, repo.get_dynamic(a.dynamic_id))
                for a in repo.list_alerts(session_id, limit)
            ]

    def list_dynamics(self) -> list[McDynamicDTO]:
        """
        Lista el catálogo activo, sembrándolo si está vacío.

        Returns:
            list[McDynamicDTO]: Dinámicas activas.
        """
        with self._session_factory() as db:
            repo = McAssistantRepository(db)
            catalog = repo.list_active_dynamics()
            if not catalog:
                seed_mc_dynamics(db)
                catalog = repo.list_active_dynamics()
            return [McDynamicDTO.model_validate(d) for d in catalog]

    def register_push_device(
        self, session_id: str, fcm_token: str, platform: str, language: str, expires_at: datetime
    ) -> None:
        """
        Registra o actualiza el dispositivo vinculado que recibirá notificaciones push.

        Args:
            session_id (str): UUID de la sesión en vivo.
            fcm_token (str): Token de Firebase del dispositivo.
            platform (str): Plataforma del dispositivo.
            language (str): Idioma de las notificaciones.
            expires_at (datetime): Expiración del monitor en UTC.
        """
        with self._session_factory() as db:
            repo = McAssistantRepository(db)
            device = repo.get_push_device_by_token(fcm_token)
            if device is None:
                device = MonitorPushDevice(fcm_token=fcm_token)
                repo.add(device)
            device.live_session_id = session_id
            device.platform = platform
            device.language = language
            device.expires_at = naive_utc(expires_at)
            db.commit()

    def push_targets(self, session_id: str, now: datetime) -> list[tuple[str, str]]:
        """
        Obtiene los dispositivos vigentes de la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.
            now (datetime): Instante actual en UTC.

        Returns:
            list[tuple[str, str]]: Pares (token Firebase, idioma).
        """
        with self._session_factory() as db:
            devices = McAssistantRepository(db).list_push_devices(session_id, naive_utc(now))
            return [(str(d.fcm_token), str(d.language)) for d in devices]

    def remove_session_push_device(self, session_id: str, fcm_token: str) -> bool:
        """
        Elimina el dispositivo push de una sesión cuando el monitor se desvincula.

        Args:
            session_id (str): UUID de la sesión autorizada.
            fcm_token (str): Token de Firebase del dispositivo.

        Returns:
            bool: True si el dispositivo existía en esa sesión y se eliminó.
        """
        with self._session_factory() as db:
            repo = McAssistantRepository(db)
            device = repo.get_push_device_by_token(fcm_token)
            if device is None or str(device.live_session_id) != session_id:
                return False
            db.delete(device)
            db.commit()
            return True

    def remove_push_tokens(self, tokens: list[str]) -> None:
        """
        Elimina dispositivos con tokens rechazados por Firebase.

        Args:
            tokens (list[str]): Tokens inválidos.
        """
        if not tokens:
            return
        with self._session_factory() as db:
            McAssistantRepository(db).delete_push_tokens(tokens)
            db.commit()


@dataclass
class SessionMcState:
    """Estado en memoria del asistente para una sesión en vivo."""

    tracker: InattentionTracker
    active_alert: McAlertDTO | None = None
    cooldown_until: datetime | None = None
    suppress_until: datetime | None = None
    pending_push: set[asyncio.Task[None]] = field(default_factory=set)


class McAssistantService:
    """
    Orquestador del Asistente MC: oyente del hub de telemetría y casos de uso de la consola.
    """

    def __init__(
        self,
        store: McAssistantStore,
        hub: LiveTelemetryHub,
        push: PushNotificationService,
        config: McAssistantConfig,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """
        Inicializa el asistente.

        Args:
            store (McAssistantStore): Operaciones de base de datos.
            hub (LiveTelemetryHub): Hub de telemetría de HU-17 por el que se emiten las alertas.
            push (PushNotificationService): Envío de notificaciones push.
            config (McAssistantConfig): Parámetros del asistente.
            clock (Callable[[], datetime]): Reloj UTC inyectable.
        """
        self.store = store
        self.hub = hub
        self.push = push
        self.config = config
        self._clock = clock
        self._states: dict[str, SessionMcState] = {}

    @staticmethod
    def event_payload(alert: McAlertDTO) -> str:
        """
        Serializa el mensaje WebSocket de una alerta.

        Args:
            alert (McAlertDTO): Alerta a emitir.

        Returns:
            str: Mensaje JSON `{"type": "mc_alert", "alert": {...}}`.
        """
        return McAlertEventDTO(alert=alert).model_dump_json()

    async def _ensure_state(self, session_id: str, now: datetime) -> SessionMcState:
        """
        Obtiene el estado de la sesión, reconstruyéndolo desde la BD la primera vez.

        Args:
            session_id (str): UUID de la sesión en vivo.
            now (datetime): Instante actual en UTC.

        Returns:
            SessionMcState: Estado del asistente para la sesión.
        """
        state = self._states.get(session_id)
        if state is not None:
            return state
        state = SessionMcState(tracker=InattentionTracker(self.config))
        self._states[session_id] = state
        lookback = self.config.window_seconds + self.config.signal_gap_seconds + 60
        try:
            context = await asyncio.to_thread(self.store.load_context, session_id)
            history = await asyncio.to_thread(
                self.store.load_history, session_id, now - timedelta(seconds=lookback)
            )
        except Exception as exc:
            logger.warning(
                "No se pudo reconstruir el asistente MC de la sesión %s: %s", session_id, exc
            )
            return state
        state.active_alert = context.active_alert
        state.suppress_until = break_window_end(context.latest_break_end, self.config)
        for sample in history:
            state.tracker.add(sample.recorded_at, sample.attention_score)
        return state

    async def on_subscribe(self, session_id: str) -> list[str]:
        """
        Envía la alerta activa a un cliente recién conectado.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            list[str]: Mensaje de la alerta activa, si existe.
        """
        state = await self._ensure_state(session_id, self._clock())
        return [self.event_payload(state.active_alert)] if state.active_alert else []

    async def on_tick(
        self, session_id: str, samples: list[MetricSample], now: datetime
    ) -> list[str]:
        """
        Evalúa la regla de desatención sostenida en cada ciclo de telemetría (HU-18).

        Args:
            session_id (str): UUID de la sesión en vivo.
            samples (list[MetricSample]): Muestras nuevas del ciclo.
            now (datetime): Instante del ciclo en UTC.

        Returns:
            list[str]: Mensajes de alertas nuevas o vencidas.
        """
        state = await self._ensure_state(session_id, now)
        for sample in samples:
            state.tracker.add(sample.recorded_at, sample.attention_score)

        active = state.active_alert
        if active is not None:
            recovered = state.tracker.low_since is None and (
                state.tracker.recovered_seconds(now) >= self.config.recovery_expire_seconds
            )
            if active.trigger == McAlertTriggerEnum.SUSTAINED_INATTENTION and recovered:
                expired = await asyncio.to_thread(
                    self.store.resolve_alert, active.id, McAlertStatusEnum.EXPIRED, now
                )
                state.active_alert = None
                return [self.event_payload(expired)]
            return []

        if state.suppress_until is not None and now < state.suppress_until:
            state.tracker.reset()
            return []
        if state.cooldown_until is not None and now < state.cooldown_until:
            return []
        if not state.tracker.is_sustained():
            return []

        alert = await asyncio.to_thread(
            self.store.create_alert,
            session_id,
            McAlertTriggerEnum.SUSTAINED_INATTENTION,
            state.tracker.average_low_attention(),
            int(state.tracker.low_duration_seconds()),
            now,
        )
        state.active_alert = alert
        state.tracker.reset()
        state.cooldown_until = now + timedelta(seconds=self.config.cooldown_seconds)
        self._schedule_push(state, alert)
        return [self.event_payload(alert)]

    def on_release(self, session_id: str) -> None:
        """
        Libera el estado de una sesión cuando su canal de telemetría se detiene.

        Args:
            session_id (str): UUID de la sesión en vivo.
        """
        self._states.pop(session_id, None)

    def _schedule_push(self, state: SessionMcState, alert: McAlertDTO) -> None:
        """
        Envía la notificación push en segundo plano para no retrasar el WebSocket.

        Args:
            state (SessionMcState): Estado de la sesión (conserva la referencia de la tarea).
            alert (McAlertDTO): Alerta recién creada.
        """
        if not self.push.enabled:
            return
        task = asyncio.create_task(self._send_push(alert))
        state.pending_push.add(task)
        task.add_done_callback(state.pending_push.discard)

    async def _send_push(self, alert: McAlertDTO) -> None:
        """
        Notifica la alerta a los celulares vinculados y elimina tokens inválidos.

        Args:
            alert (McAlertDTO): Alerta a notificar.
        """
        try:
            targets = await asyncio.to_thread(
                self.store.push_targets, alert.session_id, self._clock()
            )
            messages = [
                self.build_push_message(alert, token, language) for token, language in targets
            ]
            invalid = await asyncio.to_thread(self.push.send, messages)
            await asyncio.to_thread(self.store.remove_push_tokens, invalid)
        except Exception as exc:
            logger.warning("No se pudo enviar el push de la alerta %s: %s", alert.id, exc)

    @staticmethod
    def build_push_message(alert: McAlertDTO, token: str, language: str) -> PushMessage:
        """
        Construye la notificación push de una alerta en el idioma del dispositivo.

        Args:
            alert (McAlertDTO): Alerta a notificar.
            token (str): Token Firebase del dispositivo.
            language (str): `es` o `en`.

        Returns:
            PushMessage: Notificación con la dinámica sugerida como cuerpo.
        """
        lang = "en" if language == "en" else "es"
        dynamic = alert.dynamic
        body = (dynamic.title_en if lang == "en" else dynamic.title_es) if dynamic else ""
        return PushMessage(
            token=token,
            title=PUSH_TITLES[lang],
            body=body,
            data={"type": "mc_alert", "alert_id": alert.id, "session_id": alert.session_id},
        )

    async def _after_resolution(self, alert: McAlertDTO) -> None:
        """
        Actualiza el estado en memoria tras responder una alerta y la emite a la consola.

        Args:
            alert (McAlertDTO): Alerta actualizada.
        """
        state = self._states.get(alert.session_id)
        if state is not None:
            if state.active_alert is not None and state.active_alert.id == alert.id:
                state.active_alert = None
            if alert.break_ends_at is not None:
                state.suppress_until = break_window_end(alert.break_ends_at, self.config)
                state.tracker.reset()
        await self.hub.send_event(alert.session_id, self.event_payload(alert))

    async def apply(self, alert_id: str) -> McAlertDTO:
        """
        Marca la dinámica como aplicada; si es un descanso, inicia el temporizador de la pausa (HU-19).

        Args:
            alert_id (str): UUID de la alerta.

        Returns:
            McAlertDTO: Alerta aplicada.
        """
        alert = await asyncio.to_thread(
            self.store.resolve_alert, alert_id, McAlertStatusEnum.APPLIED, self._clock()
        )
        await self._after_resolution(alert)
        return alert

    async def dismiss(self, alert_id: str) -> McAlertDTO:
        """
        Descarta la sugerencia sin aplicarla.

        Args:
            alert_id (str): UUID de la alerta.

        Returns:
            McAlertDTO: Alerta descartada.
        """
        alert = await asyncio.to_thread(
            self.store.resolve_alert, alert_id, McAlertStatusEnum.DISMISSED, self._clock()
        )
        await self._after_resolution(alert)
        return alert

    async def next_dynamic(self, alert_id: str) -> McAlertDTO:
        """
        Cambia la dinámica sugerida de una alerta activa por otra del catálogo.

        Args:
            alert_id (str): UUID de la alerta.

        Returns:
            McAlertDTO: Alerta con la nueva dinámica.
        """
        alert = await asyncio.to_thread(self.store.replace_dynamic, alert_id)
        state = self._states.get(alert.session_id)
        if (
            state is not None
            and state.active_alert is not None
            and state.active_alert.id == alert.id
        ):
            state.active_alert = alert
        await self.hub.send_event(alert.session_id, self.event_payload(alert))
        return alert

    async def request_dynamic(self, session_id: str) -> McAlertDTO:
        """
        Crea una alerta a pedido del moderador ("Necesito una dinámica"), sin esperar la regla.

        Si ya hay una alerta activa, la devuelve en vez de crear otra.

        Args:
            session_id (str): UUID de la sesión en vivo autorizada.

        Returns:
            McAlertDTO: Alerta activa con su dinámica.
        """
        now = self._clock()
        state = await self._ensure_state(session_id, now)
        if state.active_alert is not None:
            return state.active_alert
        alert = await asyncio.to_thread(
            self.store.create_alert,
            session_id,
            McAlertTriggerEnum.MANUAL_REQUEST,
            state.tracker.smoothed_attention,
            0,
            now,
        )
        state.active_alert = alert
        await self.hub.send_event(session_id, self.event_payload(alert))
        return alert

    async def register_push_device(
        self, session_id: str, fcm_token: str, platform: str, language: str, expires_at: datetime
    ) -> PushDeviceRegisteredDTO:
        """
        Registra el celular vinculado para recibir alertas push y mantiene activo el canal de la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.
            fcm_token (str): Token de Firebase.
            platform (str): Plataforma del dispositivo.
            language (str): Idioma de las notificaciones.
            expires_at (datetime): Expiración del token de monitor en UTC.

        Returns:
            PushDeviceRegisteredDTO: Resultado del registro.
        """
        await asyncio.to_thread(
            self.store.register_push_device, session_id, fcm_token, platform, language, expires_at
        )
        self.hub.retain(session_id, as_utc(expires_at))
        return PushDeviceRegisteredDTO(
            registered=True, push_enabled=self.push.enabled, expires_at=as_utc(expires_at)
        )


_config = McAssistantConfig.from_env()
mc_assistant_service = McAssistantService(
    store=McAssistantStore(config=_config),
    hub=live_telemetry_hub,
    push=PushNotificationService(),
    config=_config,
)
live_telemetry_hub.add_listener(mc_assistant_service)


def get_mc_assistant_service() -> McAssistantService:
    """
    Dependencia de FastAPI que entrega el Asistente MC del proceso.

    Returns:
        McAssistantService: Instancia compartida.
    """
    return mc_assistant_service
