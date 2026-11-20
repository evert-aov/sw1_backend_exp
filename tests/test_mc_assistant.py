"""Pruebas de HU-18/HU-19: regla de desatención sostenida, catálogo, alertas y push; sin PostgreSQL."""

from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import BACKEND_ROOT
from app.live.dto.mc_assistant_dto import McAlertDTO, McDynamicDTO
from app.live.entity.audience_metric import AgeGroupEnum
from app.live.entity.mc_alert import McAlertStatusEnum, McAlertTriggerEnum
from app.live.entity.mc_dynamic import McDynamicModalityEnum, McDynamicTypeEnum
from app.live.service import live_telemetry_access as access
from app.live.service.live_monitor_pairing import create_monitor_token, monitor_token_expiry
from app.live.service.live_telemetry_service import LiveTelemetryHub, MetricSample
from app.live.service.mc_alert_engine import (
    DynamicOption,
    InattentionTracker,
    McAssistantConfig,
    choose_dynamic,
    modality_matches,
)
from app.live.service.mc_assistant_service import McAssistantService, SessionContext
from app.live.service.mc_dynamics_seed import CATEGORY_MC_DYNAMICS, DEFAULT_MC_DYNAMICS
from app.live.service.push_notification_service import PushMessage, PushNotificationService

SESSION_ID = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"
BASE = datetime(2026, 11, 19, 20, 0, tzinfo=timezone.utc)
CONFIG = McAssistantConfig(window_seconds=300, cooldown_seconds=300, recovery_expire_seconds=30)


def at(seconds: float) -> datetime:
    """Instante a `seconds` del inicio de la prueba."""
    return BASE + timedelta(seconds=seconds)


def feed(tracker: InattentionTracker, start: float, end: float, attention: float) -> None:
    """Agrega muestras cada 2.5 s entre `start` y `end` (incluido) con la atención indicada."""
    t = start
    while t <= end:
        tracker.add(at(t), attention)
        t += 2.5


# ---------------------------------------------------------------- regla de desatención (HU-18)


def test_alert_requires_five_minutes_of_low_attention():
    tracker = InattentionTracker(CONFIG)
    feed(tracker, 0, 295, 0.3)
    assert not tracker.is_sustained()
    feed(tracker, 297.5, 302.5, 0.3)
    assert tracker.is_sustained()
    assert tracker.average_low_attention() == pytest.approx(0.3)


def test_brief_recovery_does_not_reset_streak():
    tracker = InattentionTracker(CONFIG)
    feed(tracker, 0, 150, 0.3)
    feed(tracker, 152.5, 162.5, 0.95)  # repunte de ~10 s (menos que la tolerancia de 20 s)
    feed(tracker, 165, 305, 0.3)
    assert tracker.is_sustained()


def test_sustained_recovery_resets_streak():
    tracker = InattentionTracker(CONFIG)
    feed(tracker, 0, 150, 0.3)
    feed(tracker, 152.5, 200, 0.95)  # recuperación real de casi 50 s
    feed(tracker, 202.5, 400, 0.3)
    assert not tracker.is_sustained()


def test_camera_gap_resets_streak():
    tracker = InattentionTracker(CONFIG)
    feed(tracker, 0, 200, 0.3)
    feed(tracker, 260, 330, 0.3)  # 60 s sin métricas: la cámara se apagó
    assert not tracker.is_sustained()
    assert tracker.low_duration_seconds() == pytest.approx(70)


def test_old_or_repeated_samples_are_ignored():
    tracker = InattentionTracker(CONFIG)
    tracker.add(at(10), 0.3)
    tracker.add(at(10), 0.9)
    tracker.add(at(5), 0.9)
    assert tracker.smoothed_attention == pytest.approx(0.3)


def test_config_reads_environment(monkeypatch):
    monkeypatch.setenv("MC_ALERT_WINDOW_SECONDS", "60")
    monkeypatch.setenv("MC_ATTENTION_THRESHOLD", "no-es-numero")
    config = McAssistantConfig.from_env()
    assert config.window_seconds == 60
    assert config.attention_threshold == 0.5


# ---------------------------------------------------------------- elección de dinámica (HU-19)

CATALOG = [
    DynamicOption(str(i), d["code"], d["dynamic_type"].value, d["modality"].value, d["intensity"])
    for i, d in enumerate(DEFAULT_MC_DYNAMICS)
]


def test_seed_catalog_is_complete_and_bilingual():
    codes = [d["code"] for d in DEFAULT_MC_DYNAMICS]
    assert len(codes) == len(set(codes))
    types = {d["dynamic_type"] for d in DEFAULT_MC_DYNAMICS}
    assert types == set(McDynamicTypeEnum)
    for d in DEFAULT_MC_DYNAMICS:
        assert d["title_es"] and d["title_en"] and d["instructions_es"] and d["instructions_en"]
        assert 1 <= d["intensity"] <= 3


@pytest.mark.parametrize(
    ("dynamic", "session", "expected"),
    [
        ("ANY", "VIRTUAL", True),
        ("IN_PERSON", "IN_PERSON", True),
        ("IN_PERSON", "VIRTUAL", False),
        ("VIRTUAL", "HYBRID", False),
    ],
)
def test_modality_matching(dynamic, session, expected):
    assert modality_matches(dynamic, session) is expected


def test_virtual_event_never_gets_in_person_dynamics():
    for seed in range(30):
        chosen = choose_dynamic(CATALOG, "VIRTUAL", 0.4, [], CONFIG, random.Random(seed))
        assert chosen is not None and chosen.modality in ("ANY", "VIRTUAL")


def test_severe_drop_prefers_breaks_and_strong_reactivation():
    for seed in range(30):
        chosen = choose_dynamic(CATALOG, "IN_PERSON", 0.15, [], CONFIG, random.Random(seed))
        assert chosen is not None
        assert chosen.dynamic_type != "AUDIENCE_QUESTION" and chosen.intensity >= 2


def test_mild_drop_prefers_audience_questions_or_light_dynamics():
    for seed in range(30):
        chosen = choose_dynamic(CATALOG, "IN_PERSON", 0.45, [], CONFIG, random.Random(seed))
        assert chosen is not None
        assert chosen.dynamic_type == "AUDIENCE_QUESTION" or chosen.intensity == 1


def test_recent_dynamics_are_not_repeated_while_alternatives_exist():
    recent = [d.code for d in CATALOG if d.dynamic_type == "AUDIENCE_QUESTION"][:-1]
    chosen = choose_dynamic(CATALOG, "IN_PERSON", 0.45, recent, CONFIG, random.Random(1))
    assert chosen is not None and chosen.code not in recent


FULL_CATALOG = [
    DynamicOption(
        f"c{i}",
        d["code"],
        d["dynamic_type"].value,
        d["modality"].value,
        d["intensity"],
        tuple(d.get("category_names", [])),
    )
    for i, d in enumerate(DEFAULT_MC_DYNAMICS + CATEGORY_MC_DYNAMICS)
]


def test_category_catalog_is_valid_and_bilingual():
    codes = [d["code"] for d in DEFAULT_MC_DYNAMICS + CATEGORY_MC_DYNAMICS]
    assert len(codes) == len(set(codes))
    categories = {c for d in CATEGORY_MC_DYNAMICS for c in d["category_names"]}
    assert categories == {
        "Gastronomía",
        "Arte y Pintura",
        "Música y Conciertos",
        "Talleres y Educación",
        "Networking y Negocios",
        "Bienestar y Outdoors",
    }
    for d in CATEGORY_MC_DYNAMICS:
        assert d["title_es"] and d["title_en"] and d["instructions_es"] and d["instructions_en"]


def test_event_category_never_gets_dynamics_of_another_category():
    for seed in range(40):
        chosen = choose_dynamic(
            FULL_CATALOG,
            "IN_PERSON",
            0.45,
            [],
            CONFIG,
            random.Random(seed),
            session_category="Gastronomía",
        )
        assert chosen is not None
        assert not chosen.categories or chosen.categories == ("Gastronomía",)


def test_category_specific_dynamics_are_preferred_until_used():
    recent: list[str] = []
    chosen_codes = []
    for seed in range(6):
        chosen = choose_dynamic(
            FULL_CATALOG,
            "IN_PERSON",
            0.45,
            recent,
            CONFIG,
            random.Random(seed),
            session_category="Música y Conciertos",
        )
        assert chosen is not None
        chosen_codes.append(chosen.code)
        recent.append(chosen.code)
    music = [c for c in chosen_codes if c.startswith("MUSIC_")]
    assert music and chosen_codes[0].startswith("MUSIC_")
    assert len(set(chosen_codes)) == len(
        chosen_codes
    )  # sin repeticiones mientras haya alternativas


def test_unknown_category_uses_general_dynamics():
    chosen = choose_dynamic(
        FULL_CATALOG, "IN_PERSON", 0.45, [], CONFIG, random.Random(1), session_category=None
    )
    assert chosen is not None and chosen.categories == ()


def test_empty_catalog_returns_none():
    assert choose_dynamic([], "IN_PERSON", 0.3, [], CONFIG) is None


# ---------------------------------------------------------------- servicio del asistente


def make_dynamic(dynamic_type=McDynamicTypeEnum.AUDIENCE_QUESTION, minutes=1) -> McDynamicDTO:
    """Crea una dinámica de prueba."""
    return McDynamicDTO(
        id="dyn-1",
        code="TEST",
        dynamic_type=dynamic_type,
        modality=McDynamicModalityEnum.ANY,
        intensity=2,
        duration_minutes=minutes,
        title_es="Pregunta",
        title_en="Question",
        instructions_es="Haz una pregunta",
        instructions_en="Ask a question",
    )


class FakeStore:
    """Almacén en memoria con la misma interfaz que McAssistantStore."""

    def __init__(self, dynamic: McDynamicDTO | None = None, context: SessionContext | None = None):
        """Configura la dinámica que se propondrá y el contexto inicial."""
        self.dynamic = dynamic or make_dynamic()
        self.context = context or SessionContext(None, None)
        self.alerts: dict[str, McAlertDTO] = {}
        self.history: list[MetricSample] = []
        self.push_devices = [("token-es", "es"), ("token-en", "en")]
        self.removed: list[str] = []

    def load_context(self, session_id):
        """Devuelve el contexto configurado."""
        return self.context

    def load_history(self, session_id, since):
        """Devuelve el historial configurado."""
        return [s for s in self.history if s.recorded_at >= since]

    def create_alert(self, session_id, trigger, average_attention, low_seconds, now):
        """Crea una alerta activa en memoria."""
        alert = McAlertDTO(
            id=f"alert-{len(self.alerts) + 1}",
            session_id=session_id,
            trigger=trigger,
            status=McAlertStatusEnum.ACTIVE,
            average_attention=average_attention,
            low_attention_seconds=low_seconds,
            created_at=now,
            dynamic=self.dynamic,
        )
        self.alerts[alert.id] = alert
        return alert

    def resolve_alert(self, alert_id, new_status, now):
        """Cambia el estado y, si es un descanso aplicado, fija el fin de la pausa."""
        alert = self.alerts[alert_id]
        break_end = None
        if (
            new_status == McAlertStatusEnum.APPLIED
            and alert.dynamic
            and alert.dynamic.dynamic_type != McDynamicTypeEnum.AUDIENCE_QUESTION
        ):
            break_end = now + timedelta(minutes=alert.dynamic.duration_minutes)
        updated = alert.model_copy(
            update={"status": new_status, "resolved_at": now, "break_ends_at": break_end}
        )
        self.alerts[alert_id] = updated
        return updated

    def replace_dynamic(self, alert_id):
        """Devuelve la alerta sin cambios."""
        return self.alerts[alert_id]

    def push_targets(self, session_id, now):
        """Devuelve los dispositivos configurados."""
        return self.push_devices

    def remove_push_tokens(self, tokens):
        """Registra los tokens eliminados."""
        self.removed.extend(tokens)

    def register_push_device(self, *args):
        """No hace nada en memoria."""


class FakeHub:
    """Hub mínimo que registra los eventos emitidos y las retenciones."""

    def __init__(self):
        """Inicia sin eventos."""
        self.events: list[dict] = []
        self.retained: dict[str, datetime] = {}

    async def send_event(self, session_id, payload):
        """Guarda el evento emitido."""
        self.events.append(json.loads(payload))

    def retain(self, session_id, until):
        """Guarda la retención."""
        self.retained[session_id] = until


class FakePush:
    """Servicio push falso."""

    def __init__(self, enabled=True, invalid=None):
        """Configura si está habilitado y qué tokens rechaza."""
        self.enabled = enabled
        self.sent: list[PushMessage] = []
        self.invalid = invalid or []

    def send(self, messages):
        """Registra los mensajes y devuelve los tokens inválidos."""
        self.sent.extend(messages)
        return self.invalid


class Clock:
    """Reloj controlable."""

    def __init__(self):
        """Inicia en el instante base."""
        self.now = BASE

    def __call__(self):
        """Devuelve el instante simulado."""
        return self.now


def samples(start: float, end: float, attention: float) -> list[MetricSample]:
    """Genera muestras cada 2.5 s."""
    out, t = [], start
    while t <= end:
        out.append(MetricSample(at(t), attention, attention, 12, AgeGroupEnum.ADULT))
        t += 2.5
    return out


def make_service(store=None, push=None, config=CONFIG):
    """Crea el asistente con dobles de prueba."""
    clock = Clock()
    service = McAssistantService(
        cast(Any, store or FakeStore()),
        cast(Any, FakeHub()),
        cast(Any, push or FakePush(enabled=False)),
        config,
        clock,
    )
    return service, clock


def test_alert_is_emitted_once_after_sustained_inattention():
    async def scenario():
        service, _ = make_service()
        assert await service.on_tick(SESSION_ID, samples(0, 290, 0.3), at(290)) == []
        events = await service.on_tick(SESSION_ID, samples(292.5, 302.5, 0.3), at(302.5))
        assert len(events) == 1
        event = json.loads(events[0])
        assert event["type"] == "mc_alert"
        assert event["alert"]["trigger"] == "SUSTAINED_INATTENTION"
        assert event["alert"]["low_attention_seconds"] >= 300
        assert event["alert"]["dynamic"]["title_es"] == "Pregunta"
        # Mientras la alerta sigue activa no se crean otras
        assert await service.on_tick(SESSION_ID, samples(305, 700, 0.3), at(700)) == []

    asyncio.run(scenario())


def test_active_alert_expires_when_attention_recovers():
    async def scenario():
        service, _ = make_service()
        await service.on_tick(SESSION_ID, samples(0, 302.5, 0.3), at(302.5))
        assert await service.on_tick(SESSION_ID, samples(305, 330, 0.9), at(330)) == []
        events = await service.on_tick(SESSION_ID, samples(332.5, 365, 0.9), at(365))
        assert json.loads(events[0])["alert"]["status"] == "EXPIRED"

    asyncio.run(scenario())


def test_cooldown_prevents_back_to_back_alerts():
    async def scenario():
        service, _ = make_service()
        events = await service.on_tick(SESSION_ID, samples(0, 302.5, 0.3), at(302.5))
        alert_id = json.loads(events[0])["alert"]["id"]
        await service.dismiss(alert_id)
        # La atención sigue baja otros 5 minutos, pero aún dentro del enfriamiento
        assert await service.on_tick(SESSION_ID, samples(305, 600, 0.3), at(600)) == []
        # Pasado el enfriamiento y con una racha nueva completa, vuelve a alertar
        assert len(await service.on_tick(SESSION_ID, samples(602.5, 610, 0.3), at(610))) == 1

    asyncio.run(scenario())


def test_applied_break_suppresses_alerts_until_audience_returns():
    async def scenario():
        store = FakeStore(dynamic=make_dynamic(McDynamicTypeEnum.SHORT_BREAK, minutes=5))
        service, clock = make_service(
            store=store, config=McAssistantConfig(window_seconds=60, cooldown_seconds=0)
        )
        events = await service.on_tick(SESSION_ID, samples(0, 62.5, 0.3), at(62.5))
        clock.now = at(65)
        applied = await service.apply(json.loads(events[0])["alert"]["id"])
        assert applied.break_ends_at == at(65) + timedelta(minutes=5)
        # Durante la pausa (5 min + 60 s de regreso) no hay alertas aunque la sala esté vacía
        assert await service.on_tick(SESSION_ID, samples(67.5, 420, 0.1), at(420)) == []
        assert await service.on_tick(SESSION_ID, samples(422.5, 600, 0.1), at(600)) != []

    asyncio.run(scenario())


def test_resolution_is_broadcast_to_console():
    async def scenario():
        service, _ = make_service()
        events = await service.on_tick(SESSION_ID, samples(0, 302.5, 0.3), at(302.5))
        await service.apply(json.loads(events[0])["alert"]["id"])
        assert service.hub.events[-1]["alert"]["status"] == "APPLIED"  # type: ignore[attr-defined]

    asyncio.run(scenario())


def test_manual_request_reuses_active_alert():
    async def scenario():
        service, _ = make_service()
        first = await service.request_dynamic(SESSION_ID)
        second = await service.request_dynamic(SESSION_ID)
        assert first.id == second.id
        assert first.trigger == McAlertTriggerEnum.MANUAL_REQUEST

    asyncio.run(scenario())


def test_new_subscriber_receives_active_alert_after_restart():
    async def scenario():
        active = FakeStore().create_alert(
            SESSION_ID, McAlertTriggerEnum.SUSTAINED_INATTENTION, 0.3, 300, BASE
        )
        service, _ = make_service(store=FakeStore(context=SessionContext(active, None)))
        payloads = await service.on_subscribe(SESSION_ID)
        assert json.loads(payloads[0])["alert"]["id"] == active.id

    asyncio.run(scenario())


def test_history_is_loaded_so_a_late_console_still_alerts():
    async def scenario():
        store = FakeStore()
        store.history = samples(0, 290, 0.3)
        service, _ = make_service(store=store)
        events = await service.on_tick(SESSION_ID, samples(292.5, 302.5, 0.3), at(302.5))
        assert len(events) == 1

    asyncio.run(scenario())


def test_push_is_sent_in_device_language_and_invalid_tokens_removed():
    async def scenario():
        store = FakeStore()
        push = FakePush(enabled=True, invalid=["token-en"])
        service, _ = make_service(store=store, push=push)
        await service.on_tick(SESSION_ID, samples(0, 302.5, 0.3), at(302.5))
        await asyncio.sleep(0.05)
        bodies = {m.token: (m.title, m.body) for m in push.sent}
        assert bodies["token-es"] == ("La atención del público está bajando", "Pregunta")
        assert bodies["token-en"] == ("Audience attention is dropping", "Question")
        assert store.removed == ["token-en"]

    asyncio.run(scenario())


def test_register_push_device_retains_session_channel():
    async def scenario():
        service, _ = make_service()
        until = BASE + timedelta(hours=8)
        result = await service.register_push_device(SESSION_ID, "x" * 30, "android", "es", until)
        assert result.registered and not result.push_enabled
        assert service.hub.retained[SESSION_ID] == until  # type: ignore[attr-defined]

    asyncio.run(scenario())


# ---------------------------------------------------------------- integración con el hub de HU-17


class RecordingListener:
    """Oyente que registra las muestras y devuelve un evento por ciclo."""

    def __init__(self):
        """Inicia sin muestras."""
        self.received: list[MetricSample] = []
        self.released: list[str] = []

    async def on_subscribe(self, session_id):
        """Mensaje inicial."""
        return ['{"type":"hello"}']

    async def on_tick(self, session_id, new_samples, now):
        """Registra y emite un evento."""
        self.received.extend(new_samples)
        return ['{"type":"tick"}']

    def on_release(self, session_id):
        """Registra la liberación."""
        self.released.append(session_id)


class Subscriber:
    """Cliente WebSocket falso."""

    def __init__(self):
        """Inicia sin mensajes."""
        self.messages: list[dict] = []

    async def send_text(self, data):
        """Guarda el mensaje."""
        self.messages.append(json.loads(data))


def test_hub_feeds_listeners_and_forwards_their_events():
    async def scenario():
        data = samples(0, 5, 0.4)

        def source(session_id, after, limit):
            return [s for s in data if s.recorded_at > after]

        hub = LiveTelemetryHub(metrics_source=source, interval_seconds=60, clock=lambda: at(6))
        listener = RecordingListener()
        hub.add_listener(cast(Any, listener))
        client = Subscriber()
        await hub.subscribe(SESSION_ID, client)
        assert [m["type"] for m in client.messages] == ["telemetry", "hello"]
        await hub.broadcast(SESSION_ID)
        assert len(listener.received) == 3  # cada muestra se entrega una sola vez
        await hub.broadcast(SESSION_ID)
        assert len(listener.received) == 3
        assert client.messages[-1]["type"] == "tick"
        await hub.unsubscribe(SESSION_ID, client)
        assert listener.released == [SESSION_ID]

    asyncio.run(scenario())


def test_retained_session_keeps_running_without_clients():
    async def scenario():
        hub = LiveTelemetryHub(
            metrics_source=cast(Any, lambda *a: []), interval_seconds=0.01, clock=lambda: at(0)
        )
        listener = RecordingListener()
        hub.add_listener(cast(Any, listener))
        hub.retain(SESSION_ID, at(3600))
        assert hub.is_active(SESSION_ID)
        client = Subscriber()
        await hub.subscribe(SESSION_ID, client)
        await hub.unsubscribe(SESSION_ID, client)
        assert hub.is_active(SESSION_ID) and listener.released == []
        task = hub._tasks[SESSION_ID]
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


# ---------------------------------------------------------------- push con Firebase


def test_push_disabled_without_credentials():
    service = PushNotificationService(credentials_path="")
    assert not service.enabled
    assert service.send([PushMessage("t", "a", "b")]) == []


def test_push_payload_and_invalid_token_detection():
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append((url, json, headers))
        token = json["message"]["token"]
        if token == "gone":
            return httpx.Response(404, json={})
        if token == "unregistered":
            return httpx.Response(400, json={"error": {"details": [{"errorCode": "UNREGISTERED"}]}})
        if token == "bad-payload":
            return httpx.Response(
                400, json={"error": {"details": [{"errorCode": "INVALID_ARGUMENT"}]}}
            )
        return httpx.Response(200, json={"name": "ok"})

    service = PushNotificationService(
        post=fake_post, token_provider=lambda: ("oauth", "experiencia-demo")
    )
    invalid = service.send(
        [
            PushMessage(t, "Título", "Cuerpo", {"k": "v"})
            for t in ("ok", "gone", "unregistered", "bad-payload")
        ]
    )
    assert invalid == ["gone", "unregistered"]
    url, body, headers = calls[0]
    assert url.endswith("/projects/experiencia-demo/messages:send")
    assert headers["Authorization"] == "Bearer oauth"
    assert body["message"]["android"] == {
        "priority": "HIGH",
        "notification": {"channel_id": "mc_alerts"},
    }
    assert body["message"]["data"] == {"k": "v"}


# ---------------------------------------------------------------- acceso y migración


def test_monitor_token_expiry_only_for_monitor_tokens():
    token, expires_at = create_monitor_token(SESSION_ID, "host-1")
    assert monitor_token_expiry(token) == expires_at.replace(microsecond=0)
    assert monitor_token_expiry("no-es-token") is None


def test_session_actor_accepts_monitor_or_host():
    claims_token, _ = create_monitor_token(SESSION_ID, "host-1")
    with patch.object(access, "authorize_monitor", return_value=SESSION_ID):
        actor = access.authorize_session_actor(None, SESSION_ID, claims_token)  # type: ignore[arg-type]
    assert actor.is_monitor
    with (
        patch.object(access, "authenticate_ws_token", return_value=SimpleNamespace(id="host-1")),
        patch.object(access, "authorize_console_viewer", return_value=SESSION_ID),
    ):
        actor = access.authorize_session_actor(None, SESSION_ID, "jwt-del-anfitrion")  # type: ignore[arg-type]
    assert not actor.is_monitor


def test_alembic_history_has_single_head():
    script = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))
    assert len(script.get_heads()) == 1
    assert script.get_revision("20261119_01").down_revision == "20261025_05"


def test_remove_push_device_only_with_monitor_token():
    from app.live.control import mc_assistant_controller as controller
    from app.live.service.live_telemetry_access import SessionActor
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    removed: list[tuple[str, str]] = []
    fake_service = SimpleNamespace(
        store=SimpleNamespace(
            remove_session_push_device=lambda sid, tok: removed.append((sid, tok)) or True
        )
    )
    app = FastAPI()
    app.include_router(controller.mc_assistant_router, prefix="/api/live")
    app.dependency_overrides[controller.get_mc_assistant_service] = lambda: fake_service
    client = TestClient(app)
    body = {"fcm_token": "f" * 30}

    jwt_like = "no-es-token-de-monitor"
    response = client.post(
        "/api/live/mc/monitor/push-device/remove",
        json=body,
        headers={"Authorization": f"Bearer {jwt_like}"},
    )
    assert response.status_code == 401

    monitor, _ = create_monitor_token(SESSION_ID, "host-1")
    with patch.object(controller, "_authorize", return_value=SessionActor(SESSION_ID, True)):
        response = client.post(
            "/api/live/mc/monitor/push-device/remove",
            json=body,
            headers={"Authorization": f"Bearer {monitor}"},
        )
    assert response.status_code == 204
    assert removed == [(SESSION_ID, "f" * 30)]
