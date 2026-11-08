from __future__ import annotations

import base64
import cv2
import numpy as np
import pytest
from app.live.dto.live_dto import FramePayloadDTO, LiveMetricsDTO
from app.live.service.computer_vision_service import ComputerVisionService


def test_cv_service_empty_payload():
    service = ComputerVisionService()
    dto = FramePayloadDTO(session_id="session-test-01", image_base64="", timestamp_ms=0)
    metrics: LiveMetricsDTO = service.process_frame_ephemeral(dto)

    assert metrics.session_id == "session-test-01"
    assert metrics.detected_faces_count == 0
    assert metrics.attention_score == 0.0
    assert metrics.joy_score == 0.0
    assert metrics.inattention_score == 1.0
    assert metrics.energy_traffic_light == "RED"


def test_cv_service_blank_frame():
    service = ComputerVisionService()
    blank_img = np.zeros((240, 320, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", blank_img)
    b64_str = base64.b64encode(encoded).decode("utf-8")

    dto = FramePayloadDTO(session_id="session-test-02", frame=b64_str, timestamp_ms=1000)
    metrics: LiveMetricsDTO = service.process_frame_ephemeral(dto)

    assert metrics.session_id == "session-test-02"
    assert metrics.detected_faces_count == 0
    assert metrics.inattention_score == 1.0
    assert metrics.energy_traffic_light == "RED"


def test_traffic_light_thresholds():
    assert ComputerVisionService._compute_traffic_light(0.85) == "GREEN"
    assert ComputerVisionService._compute_traffic_light(0.70) == "GREEN"
    assert ComputerVisionService._compute_traffic_light(0.69) == "YELLOW"
    assert ComputerVisionService._compute_traffic_light(0.40) == "YELLOW"
    assert ComputerVisionService._compute_traffic_light(0.39) == "RED"
    assert ComputerVisionService._compute_traffic_light(0.0) == "RED"
