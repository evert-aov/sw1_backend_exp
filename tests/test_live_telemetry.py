"""Pruebas de HU-17: semáforo de energía, canal de telemetría cada 2.5 s y acceso a la consola; sin PostgreSQL."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.live.control import live_telemetry_controller
from app.live.control.live_telemetry_controller import live_telemetry_router
from app.live.dto.live_dto import LiveMetricsDTO
from app.live.dto.live_telemetry_dto import EnergyTrafficLightEnum, EnergyTrendEnum, SignalStatusEnum
from app.live.entity.audience_metric import AgeGroupEnum
from app.live.service import live_telemetry_access as access
from app.live.service.energy_indicator import (
    classify_energy,
    compute_energy_score,
    compute_trend,
    resolve_traffic_light,
    smooth_energy,
)
from app.live.service.live_telemetry_service import (
    PULSE_WINDOW_SIZE,
    LiveTelemetryHub,
    MetricSample,
    SessionTelemetryState,
    get_live_telemetry_hub,
)

SESSION_ID = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
BASE_TIME = datetime(2026, 11, 17, 20, 0, tzinfo=timezone.utc)

GREEN = EnergyTrafficLightEnum.GREEN
YELLOW = EnergyTrafficLightEnum.YELLOW
RED = EnergyTrafficLightEnum.RED


def sample(seconds: float, attention: float, joy: float | None = None) -> MetricSample:
    """Crea una muestra agregada a `seconds` del instante base."""
    return MetricSample(
        recorded_at=BASE_TIME + timedelta(seconds=seconds),
        attention_score=attention,
        joy_score=attention if joy is None else joy,
        detected_faces_count=12,
        dominant_age_group=AgeGroupEnum.YOUNG_ADULT,
    )


class FakeClock:
    """Reloj UTC controlable para simular el paso del tiempo."""

    def __init__(self, now: datetime = BASE_TIME):
        """Fija el instante inicial."""
        self.now = now

    def __call__(self) -> datetime:
        """Devuelve el instante simulado."""
        return self.now


class FakeSource:
    """Fuente de métricas en memoria que respeta el contrato `after`/`limit`."""

    def __init__(self):
        """Inicia sin métricas."""
        self.samples: list[MetricSample] = []

    def __call__(self, session_id: str, after: datetime, limit: int) -> list[MetricSample]:
        """Devuelve las métricas posteriores a `after`, como hace el repositorio."""
        return [s for s in self.samples if s.recorded_at > after][-limit:]


class FakeSubscriber:
    """Cliente WebSocket falso que guarda los mensajes recibidos."""

    def __init__(self, fail: bool = False):
        """Configura si el envío debe fallar como una conexión caída."""
        self.messages: list[dict] = []
        self.fail = fail

    async def send_text(self, data: str) -> None:
        """Registra el mensaje o simula una conexión cerrada."""
        if self.fail:
            raise RuntimeError("conexión cerrada")
        self.messages.append(json.loads(data))


# ---------------------------------------------------------------- indicador de energía


def test_energy_score_weights_attention_over_joy():
    assert compute_energy_score(1.0, 0.0) == 0.6
    assert compute_energy_score(0.0, 1.0) == 0.4
    assert compute_energy_score(1.5, -1.0) == 0.6  # valores fuera de rango se acotan


def test_smoothing_uses_last_four_samples():
    assert smooth_energy([]) == 0.0
    assert smooth_energy([0.0, 1.0, 1.0, 1.0, 1.0]) == 1.0
    assert smooth_energy([0.2, 0.4]) == 0.3


@pytest.mark.parametrize(
    ("score", "expected"),
    [(0.65, GREEN), (0.64, YELLOW), (0.40, YELLOW), (0.39, RED)],
)
def test_classification_thresholds(score, expected):
    assert classify_energy(score) == expected


def test_hysteresis_keeps_color_until_score_clearly_drops():
    assert resolve_traffic_light(0.62, GREEN) == GREEN  # dentro del margen: no parpadea
    assert resolve_traffic_light(0.59, GREEN) == YELLOW
    assert resolve_traffic_light(0.37, YELLOW) == YELLOW
    assert resolve_traffic_light(0.34, YELLOW) == RED
    assert resolve_traffic_light(0.20, GREEN) == RED  # una caída fuerte salta directo a rojo


def test_raising_level_is_immediate_at_threshold():
    assert resolve_traffic_light(0.40, RED) == YELLOW
    assert resolve_traffic_light(0.65, YELLOW) == GREEN
    assert resolve_traffic_light(0.5, None) == YELLOW


def test_trend_detection():
    assert compute_trend([0.5, 0.5, 0.6]) == EnergyTrendEnum.STABLE  # menos de 4 muestras
    assert compute_trend([0.4, 0.4, 0.5, 0.5]) == EnergyTrendEnum.RISING
    assert compute_trend([0.6, 0.6, 0.5, 0.5]) == EnergyTrendEnum.FALLING
    assert compute_trend([0.5, 0.51, 0.5, 0.51]) == EnergyTrendEnum.STABLE


# ---------------------------------------------------------------- estado por sesión


def test_state_ignores_repeated_or_older_samples():
    state = SessionTelemetryState(SESSION_ID)
    assert state.ingest(sample(0, 0.8))
    assert not state.ingest(sample(0, 0.1))
    assert not state.ingest(sample(-5, 0.1))
    assert len(state.pulse) == 1


def test_state_pulse_window_is_bounded():
    state = SessionTelemetryState(SESSION_ID)
    for i in range(PULSE_WINDOW_SIZE + 10):
        state.ingest(sample(i * 2.5, 0.8))
    assert len(state.pulse) == PULSE_WINDOW_SIZE


def test_single_low_sample_does_not_flip_green_light():
    state = SessionTelemetryState(SESSION_ID)
    for i in range(4):
        state.ingest(sample(i * 2.5, 0.85))
    state.ingest(sample(10, 0.30))  # un instante aislado de baja atención
    assert state.traffic_light == GREEN


def test_sustained_drop_turns_light_red():
    state = SessionTelemetryState(SESSION_ID)
    for i in range(4):
        state.ingest(sample(i * 2.5, 0.85))
    for i in range(4, 10):
        state.ingest(sample(i * 2.5, 0.15))
    assert state.traffic_light == RED


@pytest.mark.parametrize(
    ("age_seconds", "expected"),
    [(0, SignalStatusEnum.LIVE), (7.5, SignalStatusEnum.LIVE), (8, SignalStatusEnum.STALE), (31, SignalStatusEnum.NO_SIGNAL)],
)
def test_signal_status_by_metric_age(age_seconds, expected):
    state = SessionTelemetryState(SESSION_ID)
    state.ingest(sample(0, 0.8))
    assert state.signal_status(BASE_TIME + timedelta(seconds=age_seconds)) == expected


def test_empty_snapshot_reports_no_signal_without_values():
    snapshot = SessionTelemetryState(SESSION_ID).snapshot(BASE_TIME)
    assert snapshot.signal_status == SignalStatusEnum.NO_SIGNAL
    assert snapshot.traffic_light is None
    assert snapshot.energy_score is None
    assert snapshot.pulse == []
    assert snapshot.interval_seconds == 2.5


# ---------------------------------------------------------------- orquestador


def test_hub_sends_initial_snapshot_and_stops_when_last_client_leaves():
    async def scenario():
        source, clock = FakeSource(), FakeClock(BASE_TIME + timedelta(seconds=1))
        source.samples = [sample(0, 0.9)]
        hub = LiveTelemetryHub(metrics_source=source, interval_seconds=0.01, clock=clock)
        client = FakeSubscriber()

        await hub.subscribe(SESSION_ID, client)
        assert client.messages[0]["traffic_light"] == "GREEN"
        assert client.messages[0]["signal_status"] == "LIVE"

        await asyncio.sleep(0.05)
        assert len(client.messages) > 1  # emisiones periódicas

        await hub.unsubscribe(SESSION_ID, client)
        assert hub.subscriber_count(SESSION_ID) == 0
        assert SESSION_ID not in hub._tasks and SESSION_ID not in hub._states

    asyncio.run(scenario())


def test_hub_broadcasts_same_snapshot_to_all_clients_and_drops_dead_ones():
    async def scenario():
        source, clock = FakeSource(), FakeClock(BASE_TIME + timedelta(seconds=1))
        source.samples = [sample(0, 0.5)]
        hub = LiveTelemetryHub(metrics_source=source, interval_seconds=60, clock=clock)
        web, mobile, dead = FakeSubscriber(), FakeSubscriber(), FakeSubscriber()
        for client in (web, mobile, dead):
            await hub.subscribe(SESSION_ID, client)
        dead.fail = True

        source.samples.append(sample(2.5, 0.2))
        clock.now = BASE_TIME + timedelta(seconds=3)
        await hub.broadcast(SESSION_ID)

        assert web.messages[-1] == mobile.messages[-1]
        assert web.messages[-1]["attention_score"] == 0.2
        assert hub.subscriber_count(SESSION_ID) == 2
        for client in (web, mobile):
            await hub.unsubscribe(SESSION_ID, client)

    asyncio.run(scenario())


def test_publish_reaches_open_console_and_is_ignored_without_console():
    async def scenario():
        hub = LiveTelemetryHub(metrics_source=FakeSource(), interval_seconds=60, clock=FakeClock())
        metric = LiveMetricsDTO(
            session_id=SESSION_ID,
            recorded_at=BASE_TIME,
            detected_faces_count=9,
            attention_score=0.3,
            joy_score=0.3,
            neutral_score=0.4,
            inattention_score=0.7,
            dominant_age_group=AgeGroupEnum.ADULT,
            energy_traffic_light="RED",
        )
        hub.publish(SESSION_ID, metric)
        assert SESSION_ID not in hub._states  # sin consola abierta no se guarda nada

        client = FakeSubscriber()
        await hub.subscribe(SESSION_ID, client)
        hub.publish(SESSION_ID, metric)
        snapshot = await hub.broadcast(SESSION_ID)
        assert snapshot.traffic_light == RED
        assert snapshot.detected_faces_count == 9
        assert snapshot.dominant_age_group == AgeGroupEnum.ADULT
        await hub.unsubscribe(SESSION_ID, client)

    asyncio.run(scenario())


def test_rest_snapshot_without_console_does_not_keep_state():
    async def scenario():
        source = FakeSource()
        source.samples = [sample(0, 0.8)]
        hub = LiveTelemetryHub(metrics_source=source, clock=FakeClock(BASE_TIME + timedelta(seconds=1)))
        snapshot = await hub.get_snapshot(SESSION_ID)
        assert snapshot.signal_status == SignalStatusEnum.LIVE
        assert hub._states == {}

    asyncio.run(scenario())


def test_source_failure_keeps_emitting():
    async def scenario():
        def broken_source(*_args):
            raise ConnectionError("BD no disponible")

        hub = LiveTelemetryHub(metrics_source=broken_source, clock=FakeClock())
        snapshot = await hub.get_snapshot(SESSION_ID)
        assert snapshot.signal_status == SignalStatusEnum.NO_SIGNAL

    asyncio.run(scenario())


# ---------------------------------------------------------------- acceso a la consola


class FakeUserRepository:
    """Repositorio de usuarios falso con roles fijos."""

    roles: list[str] = ["HOST"]

    def __init__(self, _db):
        """Ignora la sesión de BD."""

    def get_user_roles(self, _user_id):
        """Devuelve los roles configurados."""
        return self.roles


class FakeTelemetryRepository:
    """Repositorio de telemetría falso con una sesión fija."""

    live_session = SimpleNamespace(host_id="host-1")

    def __init__(self, _db):
        """Ignora la sesión de BD."""

    def get_session(self, _session_id):
        """Devuelve la sesión configurada."""
        return self.live_session


@pytest.fixture
def fake_repositories():
    with patch.object(access, "UserRepository", FakeUserRepository), patch.object(
        access, "LiveTelemetryRepository", FakeTelemetryRepository
    ):
        FakeUserRepository.roles = ["HOST"]
        FakeTelemetryRepository.live_session = SimpleNamespace(host_id="host-1")
        yield


def test_owner_host_is_authorized(fake_repositories):
    assert access.authorize_console_viewer(None, SESSION_ID, SimpleNamespace(id="host-1")) == SESSION_ID


def test_other_host_is_forbidden(fake_repositories):
    with pytest.raises(access.TelemetryAccessError) as error:
        access.authorize_console_viewer(None, SESSION_ID, SimpleNamespace(id="host-2"))
    assert error.value.http_status == 403 and error.value.ws_close_code == 4403


def test_admin_can_watch_any_session(fake_repositories):
    FakeUserRepository.roles = ["ADMIN"]
    assert access.authorize_console_viewer(None, SESSION_ID, SimpleNamespace(id="admin")) == SESSION_ID


def test_attendee_is_forbidden(fake_repositories):
    FakeUserRepository.roles = ["ATTENDEE"]
    with pytest.raises(access.TelemetryAccessError) as error:
        access.authorize_console_viewer(None, SESSION_ID, SimpleNamespace(id="host-1"))
    assert error.value.http_status == 403


def test_missing_session_and_invalid_id(fake_repositories):
    FakeTelemetryRepository.live_session = None
    with pytest.raises(access.TelemetryAccessError) as missing:
        access.authorize_console_viewer(None, SESSION_ID, SimpleNamespace(id="host-1"))
    assert missing.value.http_status == 404
    with pytest.raises(access.TelemetryAccessError) as invalid:
        access.authorize_console_viewer(None, "no-es-uuid", SimpleNamespace(id="host-1"))
    assert invalid.value.http_status == 422


def test_websocket_requires_token():
    with pytest.raises(access.TelemetryAccessError) as error:
        access.authenticate_ws_token(None, None)
    assert error.value.ws_close_code == 4401


# ---------------------------------------------------------------- canal WebSocket


def build_app(hub: LiveTelemetryHub) -> FastAPI:
    """Crea una app mínima con el router de HU-17 y el orquestador indicado."""
    app = FastAPI()
    app.include_router(live_telemetry_router, prefix="/api")
    app.dependency_overrides[get_live_telemetry_hub] = lambda: hub
    return app


def test_websocket_streams_snapshots_and_answers_ping():
    source = FakeSource()
    now = datetime.now(timezone.utc)
    source.samples = [MetricSample(now, 0.9, 0.9, 15, AgeGroupEnum.YOUNG_ADULT)]
    hub = LiveTelemetryHub(metrics_source=source, interval_seconds=0.05)

    with patch.object(live_telemetry_controller, "_authorize_websocket", return_value=SESSION_ID):
        with TestClient(build_app(hub)).websocket_connect(f"/api/live/telemetry/ws/{SESSION_ID}?token=x") as ws:
            first = ws.receive_json()
            assert first["type"] == "telemetry"
            assert first["traffic_light"] == "GREEN"
            assert first["detected_faces_count"] == 15
            assert ws.receive_json()["type"] == "telemetry"  # emisión periódica
            ws.send_text(json.dumps({"type": "ping"}))
            while (message := ws.receive_json())["type"] != "pong":
                pass
            assert message["session_id"] == SESSION_ID


def test_websocket_closes_with_application_code_when_unauthorized():
    hub = LiveTelemetryHub(metrics_source=FakeSource())
    error = access.TelemetryAccessError(403, 4403, "No administras esta sesión en vivo")
    with patch.object(live_telemetry_controller, "_authorize_websocket", side_effect=error):
        with TestClient(build_app(hub)).websocket_connect(f"/api/live/telemetry/ws/{SESSION_ID}") as ws:
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
    assert closed.value.code == 4403


# ---------------------------------------------------------------- vinculación de monitor (tablet / celular)

from fastapi import HTTPException  # noqa: E402

from app.core.security import create_access_token, decode_token  # noqa: E402
from app.live.service.live_monitor_pairing import (  # noqa: E402
    CODE_TTL_SECONDS,
    MAX_FAILED_ATTEMPTS,
    MonitorClaims,
    MonitorPairingError,
    MonitorPairingService,
    create_monitor_token,
    decode_monitor_token,
)


class MonotonicClock:
    """Reloj monotónico controlable."""

    def __init__(self):
        """Inicia en un instante arbitrario."""
        self.now = 1000.0

    def __call__(self) -> float:
        """Devuelve el instante simulado."""
        return self.now


def test_monitor_code_is_single_use_and_case_insensitive():
    pairing = MonitorPairingService(clock=MonotonicClock())
    code, ttl = pairing.issue_code(SESSION_ID, "host-1")
    assert len(code) == 6 and ttl == CODE_TTL_SECONDS
    assert not set(code) & set("01OIL")
    claims = pairing.redeem(f" {code[:3].lower()} {code[3:]} ", "10.0.0.1")
    assert claims == MonitorClaims(session_id=SESSION_ID, host_id="host-1")
    with pytest.raises(MonitorPairingError):
        pairing.redeem(code, "10.0.0.1")


def test_monitor_code_expires():
    clock = MonotonicClock()
    pairing = MonitorPairingService(clock=clock)
    code, _ = pairing.issue_code(SESSION_ID, "host-1")
    clock.now += CODE_TTL_SECONDS + 1
    with pytest.raises(MonitorPairingError):
        pairing.redeem(code, "10.0.0.1")


def test_monitor_redeem_blocks_brute_force_per_client():
    pairing = MonitorPairingService(clock=MonotonicClock())
    code, _ = pairing.issue_code(SESSION_ID, "host-1")
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(MonitorPairingError):
            pairing.redeem("ZZZZZZ", "attacker")
    with pytest.raises(MonitorPairingError) as blocked:
        pairing.redeem(code, "attacker")
    assert blocked.value.too_many_attempts
    assert pairing.redeem(code, "tablet").session_id == SESSION_ID  # otro cliente no queda bloqueado


def test_monitor_token_roundtrip_and_isolation_from_api_tokens():
    token, _ = create_monitor_token(SESSION_ID, "host-1")
    assert decode_monitor_token(token) == MonitorClaims(session_id=SESSION_ID, host_id="host-1")
    # El token de monitor no sirve como token de la API...
    with pytest.raises(HTTPException) as rejected:
        decode_token(token)
    assert rejected.value.status_code == 401
    # ...y un token normal de la API no se interpreta como monitor
    assert decode_monitor_token(create_access_token("host-1")) is None
    assert decode_monitor_token("basura") is None


def test_monitor_token_expired_is_rejected():
    token, _ = create_monitor_token(SESSION_ID, "host-1", now=datetime.now(timezone.utc) - timedelta(days=1))
    assert decode_monitor_token(token) is None


class FakeHostRepository(FakeUserRepository):
    """Repositorio de usuarios falso que también resuelve al anfitrión por ID."""

    active = True

    def get_by_id(self, user_id):
        """Devuelve un anfitrión activo o inactivo según la configuración."""
        return SimpleNamespace(id=user_id, is_active=self.active)


@pytest.fixture
def monitor_repositories():
    with patch.object(access, "UserRepository", FakeHostRepository), patch.object(
        access, "LiveTelemetryRepository", FakeTelemetryRepository
    ):
        FakeHostRepository.active = True
        FakeTelemetryRepository.live_session = SimpleNamespace(host_id="host-1")
        yield


def test_monitor_authorized_only_for_its_session(monitor_repositories):
    claims = MonitorClaims(session_id=SESSION_ID, host_id="host-1")
    assert access.authorize_monitor(None, SESSION_ID, claims) == SESSION_ID
    with pytest.raises(access.TelemetryAccessError) as other:
        access.authorize_monitor(None, "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5c", claims)
    assert other.value.ws_close_code == 4403


def test_monitor_revoked_when_host_changes_or_is_deactivated(monitor_repositories):
    claims = MonitorClaims(session_id=SESSION_ID, host_id="host-1")
    FakeHostRepository.active = False
    with pytest.raises(access.TelemetryAccessError):
        access.authorize_monitor(None, SESSION_ID, claims)
    FakeHostRepository.active = True
    FakeTelemetryRepository.live_session = SimpleNamespace(host_id="host-2")
    with pytest.raises(access.TelemetryAccessError):
        access.authorize_monitor(None, SESSION_ID, claims)
