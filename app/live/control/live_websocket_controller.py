from __future__ import annotations

import json
import logging
from typing import Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db, SessionLocal
from app.experience.entity.experience import Experience
from app.live.dto.live_dto import (
    LiveSessionCreateDTO,
    LiveSessionResponseDTO,
    LiveMetricsDTO,
    ConsentDTO,
    ActionSuggestionDTO,
    FramePayloadDTO,
)
from app.live.entity.live_session import LiveSession, LiveSessionStatusEnum
from app.live.entity.audience_metric import AudienceMetric
from app.live.entity.consent import Consent
from app.live.repository.live_repositories import (
    LiveSessionRepository,
    AudienceMetricRepository,
    ConsentRepository,
    LiveSuggestionRepository,
)
from app.live.service.computer_vision_service import ComputerVisionService

logger = logging.getLogger(__name__)

live_router = APIRouter(prefix="/live", tags=["Live & WebSocket Controller (CU-08, CU-09, CU-10, CU-11)"])


class LiveConnectionManager:
    """Gestor de conexiones WebSocket multi-cliente organizado por sesión (CU-08, CU-09)."""

    def __init__(self) -> None:
        self.active_rooms: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if session_id not in self.active_rooms:
            self.active_rooms[session_id] = []
        self.active_rooms[session_id].append(websocket)
        logger.info(f"WebSocket conectado a sesión {session_id}. Total clientes: {len(self.active_rooms[session_id])}")

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        if session_id in self.active_rooms:
            if websocket in self.active_rooms[session_id]:
                self.active_rooms[session_id].remove(websocket)
            if not self.active_rooms[session_id]:
                del self.active_rooms[session_id]
        logger.info(f"WebSocket desconectado de sesión {session_id}")

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        if session_id in self.active_rooms:
            dead_connections: list[WebSocket] = []
            for connection in self.active_rooms[session_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    dead_connections.append(connection)
            for dead in dead_connections:
                self.disconnect(session_id, dead)


ws_manager = LiveConnectionManager()


@live_router.post("/session", response_model=LiveSessionResponseDTO, status_code=status.HTTP_201_CREATED)
def start_live_session(dto: LiveSessionCreateDTO, db: Session = Depends(get_db)):
    """Inicia o recupera una sesión de transmisión en vivo vinculada a una experiencia (CU-08)."""
    experience = db.query(Experience).filter(Experience.id == dto.experience_id).first()
    if not experience:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiencia con ID {dto.experience_id} no encontrada.",
        )

    session_repo = LiveSessionRepository(db)
    # Verificar si ya existe una sesión activa para esta experiencia
    existing = (
        db.query(LiveSession)
        .filter(
            LiveSession.experience_id == dto.experience_id,
            LiveSession.status.in_([LiveSessionStatusEnum.INITIALIZED, LiveSessionStatusEnum.ACTIVE]),
        )
        .first()
    )
    if existing:
        return LiveSessionResponseDTO.model_validate(existing)

    host_id = dto.host_id or experience.host_id
    new_session = LiveSession(
        experience_id=dto.experience_id,
        host_id=host_id,
        status=LiveSessionStatusEnum.ACTIVE,
    )
    saved_session = session_repo.create(new_session)
    return LiveSessionResponseDTO.model_validate(saved_session)


@live_router.post("/consent", status_code=status.HTTP_200_OK)
def record_gdpr_consent(dto: ConsentDTO, db: Session = Depends(get_db)):
    """Registra el consentimiento informado del asistente bajo GDPR para análisis efímero en RAM (HU-14)."""
    session_repo = LiveSessionRepository(db)
    session = session_repo.get_by_id(dto.session_id)
    if not session:
        return {
            "status": "CONSENT_RECORDED_DEMO",
            "session_id": dto.session_id,
            "accepted": dto.accepted,
            "gdpr_compliant": True,
        }

    user_id = dto.user_id or session.host_id
    consent_repo = ConsentRepository(db)
    consent = Consent(
        live_session_id=dto.session_id,
        user_id=user_id,
        accepted=dto.accepted,
        consent_type=dto.consent_type,
    )
    consent_repo.record_consent(consent)
    return {
        "status": "CONSENT_RECORDED",
        "session_id": dto.session_id,
        "accepted": dto.accepted,
        "gdpr_compliant": True,
    }


@live_router.get("/sessions/{session_id}/suggestions", response_model=list[ActionSuggestionDTO])
def get_session_suggestions(session_id: str, db: Session = Depends(get_db)):
    """Consulta las sugerencias dinámicas emitidas durante la sesión (CU-10, CU-11)."""
    repo = LiveSuggestionRepository(db)
    suggestions = repo.get_by_session(session_id)
    return [ActionSuggestionDTO.model_validate(s) for s in suggestions]


@live_router.websocket("/ws/{session_id}")
async def live_stream_websocket(websocket: WebSocket, session_id: str):
    """
    Canal WebSocket para ingesta de fotogramas efímeros (HU-13, HU-14)
    y emisión reactiva del Engagement Score hacia el Dashboard del moderador (HU-15).
    """
    await ws_manager.connect(session_id, websocket)
    cv_service = ComputerVisionService()

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload_dict = json.loads(data)
            except Exception:
                continue

            # Inyectar session_id de la ruta si no viene en el payload
            if "session_id" not in payload_dict:
                payload_dict["session_id"] = session_id

            try:
                frame_dto = FramePayloadDTO.model_validate(payload_dict)
            except Exception as e:
                logger.warning(f"Payload inválido recibido por WebSocket: {e}")
                continue

            # Procesamiento efímero en RAM (HU-14, HU-15)
            metrics_dto: LiveMetricsDTO = cv_service.process_frame_ephemeral(frame_dto)

            # Persistencia de métricas numéricas agregadas si la sesión existe en BD
            try:
                with SessionLocal() as db:
                    session_exists = db.query(LiveSession).filter(LiveSession.id == session_id).first()
                    if session_exists:
                        metric_entity = AudienceMetric(
                            live_session_id=session_id,
                            recorded_at=metrics_dto.recorded_at,
                            detected_faces_count=metrics_dto.detected_faces_count,
                            attention_score=metrics_dto.attention_score,
                            joy_score=metrics_dto.joy_score,
                            neutral_score=metrics_dto.neutral_score,
                            inattention_score=metrics_dto.inattention_score,
                            dominant_age_group=metrics_dto.dominant_age_group,
                        )
                        AudienceMetricRepository(db).save_metric(metric_entity)
            except Exception as db_err:
                logger.warning(f"No se persistió métrica en BD para sesión {session_id}: {db_err}")

            # Emisión reactiva a todos los clientes del dashboard
            await ws_manager.broadcast(session_id, metrics_dto.model_dump(mode="json"))

    except WebSocketDisconnect:
        ws_manager.disconnect(session_id, websocket)
    except Exception as exc:
        logger.error(f"Error inesperado en WebSocket sesión {session_id}: {exc}")
        ws_manager.disconnect(session_id, websocket)
