from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.experience.entity.experience import Experience
from app.live.control.live_websocket_controller import (
    BROADCAST_INTERVAL_SECONDS,
    LiveConnectionManager,
    compute_energy_traffic_light,
    manager,
)
from app.live.dto.live_dto import FramePayloadDTO, LiveMetricsDTO
from app.live.entity.audience_metric import AgeGroupEnum, AudienceMetric
from app.live.entity.live_session import LiveSession, LiveSessionStatusEnum
from app.live.repository.live_repositories import (
    AudienceMetricRepository,
    ConsentRepository,
    LiveSessionRepository,
)
from app.live.service.computer_vision_service import ComputerVisionService
from main import app

client = TestClient(app)


def test_traffic_light_thresholds():
    """Verifica los umbrales discretos del semáforo de energía (HU-17)."""
    # >= 0.70 -> GREEN
    assert compute_energy_traffic_light(0.70) == "GREEN"
    assert compute_energy_traffic_light(0.85) == "GREEN"
    assert compute_energy_traffic_light(1.00) == "GREEN"

    # 0.40 a 0.69 -> YELLOW
    assert compute_energy_traffic_light(0.69) == "YELLOW"
    assert compute_energy_traffic_light(0.55) == "YELLOW"
    assert compute_energy_traffic_light(0.40) == "YELLOW"

    # < 0.40 -> RED
    assert compute_energy_traffic_light(0.39) == "RED"
    assert compute_energy_traffic_light(0.20) == "RED"
    assert compute_energy_traffic_light(0.00) == "RED"


def test_broadcast_interval_is_2_and_half_seconds():
    """Valida que el broadcasting esté configurado a exactamente 2.5 segundos (HU-17)."""
    assert BROADCAST_INTERVAL_SECONDS == 2.5


def test_live_session_repository_crud():
    """Prueba unitaria de repositorio de sesión en vivo con sesión mockeada."""
    db = MagicMock()
    repo = LiveSessionRepository(db)

    session = LiveSession(
        id=str(uuid4()),
        experience_id=str(uuid4()),
        host_id=str(uuid4()),
        status=LiveSessionStatusEnum.ACTIVE,
    )
    repo.create(session)
    db.add.assert_called_once_with(session)
    db.commit.assert_called_once()


def test_audience_metric_repository_crud():
    """Prueba unitaria de repositorio de métricas agregadas."""
    db = MagicMock()
    repo = AudienceMetricRepository(db)

    metric = AudienceMetric(
        live_session_id=str(uuid4()),
        detected_faces_count=18,
        attention_score=0.82,
        joy_score=0.75,
        neutral_score=0.18,
        inattention_score=0.07,
    )
    repo.save_metric(metric)
    db.add.assert_called_once_with(metric)
    db.commit.assert_called_once()


def test_cv_service_process_frame_ephemeral():
    """Prueba que el procesamiento de frames genere LiveMetricsDTO sin conservar la imagen."""
    db = MagicMock()
    cv_service = ComputerVisionService(db)

    # Frame simulado con bytes mínimos
    dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    session_id = str(uuid4())
    dto = FramePayloadDTO(session_id=session_id, image_base64=dummy_b64, timestamp_ms=1000)

    result = cv_service.process_frame_ephemeral(dto)

    assert isinstance(result, LiveMetricsDTO)
    assert result.session_id == session_id
    assert 0.0 <= result.attention_score <= 1.0
    assert result.energy_traffic_light in ("GREEN", "YELLOW", "RED")
    assert result.detected_faces_count > 0


def test_start_session_endpoint_not_found():
    """El endpoint retorna 404 si la experiencia no existe."""
    fake_exp_id = str(uuid4())
    response = client.post("/api/live/session", json={"experience_id": fake_exp_id})
    assert response.status_code == 404
    assert "no existe" in response.json()["detail"]


def test_start_session_endpoint_success():
    """El endpoint inicializa o recupera la sesión activa cuando la experiencia existe."""
    db = SessionLocal()
    try:
        exp = db.query(Experience).first()
        if not exp:
            pytest.skip("No hay experiencias en la base de datos de prueba.")

        response = client.post("/api/live/session", json={"experience_id": exp.id})
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["experience_id"] == exp.id
        assert data["status"] == "ACTIVE"
    finally:
        db.close()


def test_gdpr_consent_endpoint():
    """El endpoint de consentimiento GDPR valida existencia y registra aceptación."""
    db = SessionLocal()
    try:
        session = db.query(LiveSession).first()
        if not session:
            # Crear una sesión para la prueba
            exp = db.query(Experience).first()
            if not exp:
                pytest.skip("No hay experiencias en la base de datos.")
            session = LiveSession(
                experience_id=exp.id,
                host_id=exp.host_id,
                status=LiveSessionStatusEnum.ACTIVE,
            )
            db.add(session)
            db.commit()
            db.refresh(session)

        response = client.post(
            "/api/live/consent",
            json={
                "session_id": session.id,
                "accepted": True,
                "consent_type": "GDPR_EPHEMERAL_VIDEO_ANALYSIS",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["accepted"] is True
    finally:
        db.close()


def test_latest_metrics_endpoint():
    """El endpoint REST de última telemetría retorna LiveMetricsDTO válido."""
    test_session_id = str(uuid4())
    response = client.get(f"/api/live/sessions/{test_session_id}/latest-metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == test_session_id
    assert "attention_score" in data
    assert "energy_traffic_light" in data
    assert data["energy_traffic_light"] in ("GREEN", "YELLOW", "RED")


def test_websocket_stream_connect_and_receive():
    """Prueba la conexión al canal WebSocket y la recepción inmediata de telemetría agregada."""
    test_session_id = str(uuid4())
    with client.websocket_connect(f"/api/live/ws/{test_session_id}") as ws:
        # Primer mensaje debe llegar inmediatamente sin esperar 2.5s
        initial_data = ws.receive_text()
        parsed = json.loads(initial_data)
        assert parsed["session_id"] == test_session_id
        assert "attention_score" in parsed
        assert "energy_traffic_light" in parsed
        assert parsed["energy_traffic_light"] in ("GREEN", "YELLOW", "RED")

        # Enviar un ping y verificar pong
        ws.send_text(json.dumps({"type": "ping"}))
        pong_data = ws.receive_text()
        pong_parsed = json.loads(pong_data)
        assert pong_parsed.get("type") == "pong"

