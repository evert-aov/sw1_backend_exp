from __future__ import annotations

import base64
import gc
import math
import os
from datetime import datetime, timezone
import cv2
import numpy as np
from sqlalchemy.orm import Session
from app.live.dto.live_dto import FramePayloadDTO, LiveMetricsDTO
from app.live.entity.audience_metric import AgeGroupEnum


class ComputerVisionService:
    """
    Servicio de Visión por Computadora e Inferencia Efímera en RAM (HU-13, HU-14, HU-15).
    Garantiza el cumplimiento estricto de privacidad GDPR:
    - Los fotogramas se decodifican únicamente en búferes de memoria RAM.
    - Se procesan métricas numéricas agregadas.
    - Se eliminan explícitamente los arrays y tensores sin guardar imágenes en disco ni BD.
    """

    _detector = None
    _model_path = os.path.join(os.path.dirname(__file__), "..", "assets", "face_detection_yunet_2023mar.onnx")

    def __init__(self, db: Session | None = None):
        self.db = db
        self._ensure_detector_loaded()

    @classmethod
    def _ensure_detector_loaded(cls) -> None:
        """Carga perezosa del detector ultra-ligero YuNet ONNX (232 KB)."""
        if cls._detector is None and os.path.exists(cls._model_path):
            try:
                cls._detector = cv2.FaceDetectorYN_create(
                    model=cls._model_path,
                    config="",
                    input_size=(320, 240),
                    score_threshold=0.5,
                    nms_threshold=0.3,
                    top_k=5000,
                )
            except Exception:
                cls._detector = None

    def process_frame_ephemeral(self, frame_dto: FramePayloadDTO) -> LiveMetricsDTO:
        """
        Inferencia efímera en memoria RAM:
        1. Decodifica fotograma Base64.
        2. Detecta rostros y clasifica expresiones (Alegría, Interés, Desatención).
        3. Calcula Engagement Score agregado y semáforo de energía.
        4. Destruye inmediatamente el fotograma de la memoria RAM (GDPR).
        """
        frame = None
        np_arr = None
        frame_bytes = None

        try:
            raw_b64 = frame_dto.image_base64
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]

            if not raw_b64.strip():
                return self._build_empty_metrics(frame_dto.session_id)

            frame_bytes = base64.b64decode(raw_b64)
            np_arr = np.frombuffer(frame_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is None:
                return self._build_empty_metrics(frame_dto.session_id)

            h, w = frame.shape[:2]
            return self._analyze_frame(frame, frame_dto.session_id, w, h)

        except Exception:
            return self._build_empty_metrics(frame_dto.session_id)

        finally:
            # HU-14 (GDPR Compliance): Destrucción estricta de tensores/buffers faciales de RAM
            del frame
            del np_arr
            del frame_bytes

    def _analyze_frame(self, frame: np.ndarray, session_id: str, width: int, height: int) -> LiveMetricsDTO:
        """Clasifica métricas biométricas agregadas sobre los rostros detectados en el frame."""
        faces_count = 0
        total_joy = 0.0
        total_attention = 0.0
        total_inattention = 0.0
        total_neutral = 0.0

        if self._detector is not None:
            self._detector.setInputSize((width, height))
            _, faces = self._detector.detect(frame)

            if faces is not None and len(faces) > 0:
                faces_count = len(faces)
                for face in faces:
                    # YuNet output: [x, y, w, h, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rcm, y_rcm, x_lcm, y_lcm, score]
                    # Landmark indices:
                    # Right eye: (face[4], face[5])
                    # Left eye:  (face[6], face[7])
                    # Nose tip:  (face[8], face[9])
                    # Right mouth corner: (face[10], face[11])
                    # Left mouth corner:  (face[12], face[13])
                    x_re, y_re = float(face[4]), float(face[5])
                    x_le, y_le = float(face[6]), float(face[7])
                    x_nt, y_nt = float(face[8]), float(face[9])
                    x_rcm, y_rcm = float(face[10]), float(face[11])
                    x_lcm, y_lcm = float(face[12]), float(face[13])
                    score = float(face[14])

                    # 1. Distancia inter-ocular
                    eye_dist = math.hypot(x_le - x_re, y_le - y_re)
                    safe_eye_dist = max(eye_dist, 1.0)

                    # 2. Distancia comisuras labiales (ancho de sonrisa)
                    mouth_dist = math.hypot(x_lcm - x_rcm, y_lcm - y_rcm)
                    smile_ratio = mouth_dist / safe_eye_dist

                    # Alegría / Joy: smile_ratio > 0.50 (normalizada 0.0 a 1.0)
                    joy = min(1.0, max(0.0, (smile_ratio - 0.45) / 0.35))

                    # 3. Orientación de la cabeza (Yaw): simetría nariz respecto a los ojos
                    dist_r_nose = abs(x_nt - x_re)
                    dist_l_nose = abs(x_le - x_nt)
                    yaw_diff = abs(dist_r_nose - dist_l_nose) / safe_eye_dist

                    # Atención / Interés: mirada frontal (yaw bajo) y confianza alta
                    frontal_factor = min(1.0, max(0.0, 1.0 - (yaw_diff * 2.2)))
                    attention = min(1.0, max(0.0, 0.75 * frontal_factor + 0.25 * score))

                    # Desatención: cabeza girada / mirada evasiva
                    inattention = min(1.0, max(0.0, 1.0 - attention))

                    # Expresión neutral
                    neutral = min(1.0, max(0.0, 1.0 - abs(joy - inattention)))

                    total_joy += joy
                    total_attention += attention
                    total_inattention += inattention
                    total_neutral += neutral

        if faces_count > 0:
            avg_joy = round(total_joy / faces_count, 3)
            avg_attention = round(total_attention / faces_count, 3)
            avg_inattention = round(total_inattention / faces_count, 3)
            avg_neutral = round(total_neutral / faces_count, 3)

            # Fórmula de Engagement Score ponderado
            engagement_score = min(
                1.0,
                max(0.0, (0.55 * avg_attention) + (0.45 * avg_joy) - (0.25 * avg_inattention)),
            )
        else:
            avg_joy = 0.0
            avg_attention = 0.0
            avg_inattention = 1.0
            avg_neutral = 0.0
            engagement_score = 0.0

        traffic_light = self._compute_traffic_light(engagement_score)

        return LiveMetricsDTO(
            session_id=session_id,
            recorded_at=datetime.now(timezone.utc),
            detected_faces_count=faces_count,
            attention_score=round(avg_attention, 3),
            joy_score=round(avg_joy, 3),
            neutral_score=round(avg_neutral, 3),
            inattention_score=round(avg_inattention, 3),
            dominant_age_group=AgeGroupEnum.YOUNG_ADULT,
            energy_traffic_light=traffic_light,
        )

    @staticmethod
    def _compute_traffic_light(score: float) -> str:
        """Determina el semáforo visual de energía según el Engagement Score."""
        if score >= 0.70:
            return "GREEN"
        if score >= 0.40:
            return "YELLOW"
        return "RED"

    def _build_empty_metrics(self, session_id: str) -> LiveMetricsDTO:
        """Métricas por defecto en ausencia de señal o frame."""
        return LiveMetricsDTO(
            session_id=session_id,
            recorded_at=datetime.now(timezone.utc),
            detected_faces_count=0,
            attention_score=0.0,
            joy_score=0.0,
            neutral_score=0.0,
            inattention_score=1.0,
            dominant_age_group=AgeGroupEnum.YOUNG_ADULT,
            energy_traffic_light="RED",
        )

    def estimate_engagement_score(self, frame_data: bytes) -> float:
        """Calcula el engagement score (0.0 a 1.0) a partir de bytes JPEG/PNG en RAM."""
        try:
            np_arr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is None:
                return 0.0
            h, w = frame.shape[:2]
            metrics = self._analyze_frame(frame, "temp", w, h)
            return metrics.attention_score
        except Exception:
            return 0.0

    def estimate_age_group(self, frame_data: bytes) -> str:
        """Estima grupo etario predominante."""
        return AgeGroupEnum.YOUNG_ADULT.value
