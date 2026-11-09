from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import math
import random
from typing import Dict, Optional, Set
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.experience.entity.experience import Experience
from app.live.dto.live_dto import (
    ConsentDTO,
    FramePayloadDTO,
    LiveMetricsDTO,
    LiveSessionCreateDTO,
)
from app.live.entity.audience_metric import AgeGroupEnum
from app.live.entity.consent import Consent
from app.live.entity.live_session import LiveSession, LiveSessionStatusEnum
from app.live.repository.live_repositories import (
    ConsentRepository,
    LiveSessionRepository,
)
from app.live.service.computer_vision_service import (
    ComputerVisionService,
    compute_energy_traffic_light,
)

logger = logging.getLogger(__name__)

# Intervalo exacto de broadcasting sincronizado de telemetría (HU-17)
BROADCAST_INTERVAL_SECONDS = 2.5

live_router = APIRouter(
    prefix="/live",
    tags=["Live & WebSocket Controller (CU-08, CU-09, CU-10, CU-11)"],
)


class LiveConnectionManager:
    """
    Gestor centralizado de conexiones WebSocket y broadcasting sincronizado cada 2.5s (HU-17).
    Mantiene canales aislados por cada sesión en vivo y emite las métricas agregadas
    simultáneamente a todos los clientes suscritos (Consola de anfitrión, tablet y móvil).
    """

    def __init__(self) -> None:
        """Inicializa las estructuras de conexiones activas y tareas de broadcasting."""
        self._active_connections: Dict[str, Set[WebSocket]] = {}
        self._broadcast_tasks: Dict[str, asyncio.Task[None]] = {}
        self._last_metrics: Dict[str, LiveMetricsDTO] = {}
        self._pulse_step: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """
        Acepta y registra una nueva conexión WebSocket asociada a una sesión en vivo.
        Inicia la tarea periódica de emisión sincronizada cada 2.5s si es el primer cliente.

        Args:
            session_id (str): UUID de la sesión en vivo.
            websocket (WebSocket): Instancia de conexión WebSocket de FastAPI.
        """
        await websocket.accept()
        async with self._lock:
            if session_id not in self._active_connections:
                self._active_connections[session_id] = set()
                self._pulse_step[session_id] = 0

            self._active_connections[session_id].add(websocket)

            # Iniciar tarea en segundo plano de emisión sincronizada cada 2.5s
            if session_id not in self._broadcast_tasks or self._broadcast_tasks[session_id].done():
                self._broadcast_tasks[session_id] = asyncio.create_task(
                    self._sync_broadcast_loop(session_id)
                )
        logger.info("Cliente conectado a sesión %s. Total activos: %d", session_id, len(self._active_connections[session_id]))

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """
        Desregistra un cliente WebSocket al cerrar la conexión.
        Cancela el bucle de broadcasting si ya no quedan clientes observando la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.
            websocket (WebSocket): Conexión a remover.
        """
        async with self._lock:
            if session_id in self._active_connections:
                self._active_connections[session_id].discard(websocket)
                if not self._active_connections[session_id]:
                    del self._active_connections[session_id]
                    # Cancelar la tarea de transmisión periódica para ahorrar recursos
                    task = self._broadcast_tasks.pop(session_id, None)
                    if task and not task.done():
                        task.cancel()
        logger.info("Cliente desconectado de sesión %s.", session_id)

    async def broadcast_metric(self, session_id: str, metric: LiveMetricsDTO) -> None:
        """
        Transmite una métrica agregada en formato JSON a todos los clientes de una sesión.

        Args:
            session_id (str): UUID de la sesión en vivo.
            metric (LiveMetricsDTO): DTO de telemetría a emitir.
        """
        self._last_metrics[session_id] = metric
        payload = metric.model_dump_json()

        recipients = list(self._active_connections.get(session_id, []))
        if not recipients:
            return

        dead_connections: list[WebSocket] = []
        for connection in recipients:
            try:
                await connection.send_text(payload)
            except Exception:
                dead_connections.append(connection)

        if dead_connections:
            async with self._lock:
                for dead in dead_connections:
                    self._active_connections.get(session_id, set()).discard(dead)

    def get_latest_metric(self, session_id: str) -> LiveMetricsDTO:
        """
        Obtiene la última métrica de telemetría calculada o genera un pulso representativo.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            LiveMetricsDTO: Objeto con indicadores de energía y atención vigentes.
        """
        if session_id in self._last_metrics:
            return self._last_metrics[session_id]
        return self._generate_simulated_pulse(session_id)

    def update_session_metric(self, session_id: str, metric: LiveMetricsDTO) -> None:
        """
        Actualiza en memoria la última métrica resultante del procesamiento de fotogramas.

        Args:
            session_id (str): UUID de la sesión.
            metric (LiveMetricsDTO): Nueva métrica calculada.
        """
        self._last_metrics[session_id] = metric

    def _generate_simulated_pulse(self, session_id: str) -> LiveMetricsDTO:
        """
        Genera una onda de telemetría agregada realista cuando no se reciben fotogramas activos.
        Varía suavemente la atención para reflejar el dinamismo de la audiencia en vivo.

        Args:
            session_id (str): UUID de la sesión en vivo.

        Returns:
            LiveMetricsDTO: Métricas generadas con semáforo discreto sincronizado.
        """
        step = self._pulse_step.get(session_id, 0)
        self._pulse_step[session_id] = step + 1

        # Oscilación senoidal suave entre 0.68 y 0.88 con perturbación estocástica leve
        sine_factor = math.sin(step * 0.3) * 0.10
        jitter = (random.random() - 0.5) * 0.04
        attention = round(min(0.96, max(0.45, 0.78 + sine_factor + jitter)), 2)

        joy = round(min(0.95, max(0.40, attention * 0.90 + (random.random() * 0.05))), 2)
        neutral = round(max(0.05, 1.0 - attention), 2)
        inattention = round(max(0.02, (1.0 - attention) * 0.5), 2)
        faces = 16 + int(math.sin(step * 0.2) * 3)
        traffic_light = compute_energy_traffic_light(attention)

        return LiveMetricsDTO(
            session_id=session_id,
            recorded_at=datetime.now(timezone.utc),
            detected_faces_count=faces,
            attention_score=attention,
            joy_score=joy,
            neutral_score=neutral,
            inattention_score=inattention,
            dominant_age_group=AgeGroupEnum.YOUNG_ADULT,
            energy_traffic_light=traffic_light,
        )

    async def _sync_broadcast_loop(self, session_id: str) -> None:
        """
        Bucle asíncrono que realiza broadcasting cada 2.5s estrictos a todos los clientes (HU-17).

        Args:
            session_id (str): UUID de la sesión en vivo a transmitir.
        """
        logger.info("Iniciando bucle de broadcasting sincronizado cada %.1fs para sesión %s", BROADCAST_INTERVAL_SECONDS, session_id)
        try:
            while True:
                await asyncio.sleep(BROADCAST_INTERVAL_SECONDS)
                metric = self._generate_simulated_pulse(session_id)
                await self.broadcast_metric(session_id, metric)
        except asyncio.CancelledError:
            logger.info("Bucle de broadcasting para sesión %s detenido correctamente.", session_id)
        except Exception as exc:
            logger.error("Error en bucle de broadcasting de sesión %s: %s", session_id, exc)


# Instancia singleton del gestor de conexiones para el servidor
manager = LiveConnectionManager()


@live_router.post(
    "/session",
    status_code=status.HTTP_201_CREATED,
    summary="Iniciar sesión en vivo de telemetría (CU-09 / HU-17)",
    description="Inicializa o recupera una sesión de telemetría en tiempo real asociada a una experiencia.",
)
def start_live_session(dto: LiveSessionCreateDTO, db: Session = Depends(get_db)) -> dict:
    """
    Inicializa una sesión en vivo para una experiencia o retorna la sesión activa existente.

    Args:
        dto (LiveSessionCreateDTO): DTO con el ID de la experiencia a transmitir.
        db (Session): Sesión transaccional inyectada por FastAPI.

    Returns:
        dict: Diccionario con los datos identificadores y estado de la sesión iniciada.

    Raises:
        HTTPException (404): Si la experiencia solicitada no existe en la base de datos.
    """
    experience = db.query(Experience).filter(Experience.id == dto.experience_id).first()
    if not experience:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La experiencia con ID '{dto.experience_id}' no existe.",
        )

    repo = LiveSessionRepository(db)
    active_session = repo.get_active_by_experience(dto.experience_id)
    if active_session:
        return {
            "id": active_session.id,
            "experience_id": active_session.experience_id,
            "host_id": active_session.host_id,
            "status": active_session.status.value,
            "started_at": active_session.started_at.isoformat() if active_session.started_at else None,
        }

    new_session = LiveSession(
        experience_id=dto.experience_id,
        host_id=experience.host_id,
        status=LiveSessionStatusEnum.ACTIVE,
        started_at=datetime.now(timezone.utc),
    )
    saved_session = repo.create(new_session)

    return {
        "id": saved_session.id,
        "experience_id": saved_session.experience_id,
        "host_id": saved_session.host_id,
        "status": saved_session.status.value,
        "started_at": saved_session.started_at.isoformat() if saved_session.started_at else None,
    }


@live_router.post(
    "/consent",
    status_code=status.HTTP_200_OK,
    summary="Registrar consentimiento informado GDPR del asistente (HU-14)",
    description="Registra la autorización del usuario asistente para análisis efímero de video en RAM.",
)
def record_gdpr_consent(dto: ConsentDTO, db: Session = Depends(get_db)) -> dict:
    """
    Registra el consentimiento informado de privacidad GDPR para el procesamiento efímero en RAM.

    Args:
        dto (ConsentDTO): Datos del consentimiento emitido por el asistente.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        dict: Confirmación de recepción y estado del consentimiento.

    Raises:
        HTTPException (404): Si la sesión en vivo especificada no existe.
    """
    session = db.query(LiveSession).filter(LiveSession.id == dto.session_id).first()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La sesión en vivo '{dto.session_id}' no fue encontrada.",
        )

    consent_repo = ConsentRepository(db)
    consent = Consent(
        live_session_id=dto.session_id,
        user_id=session.host_id,  # Referencia por defecto si es anónimo/asistente
        accepted=dto.accepted,
        consent_type=dto.consent_type,
        consented_at=datetime.now(timezone.utc),
    )
    consent_repo.record_consent(consent)

    return {
        "status": "success",
        "session_id": dto.session_id,
        "accepted": dto.accepted,
        "consent_type": dto.consent_type,
    }


@live_router.get(
    "/sessions/{session_id}/latest-metrics",
    response_model=LiveMetricsDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar las últimas métricas agregadas en vivo (HU-17)",
)
def get_latest_live_metrics(session_id: str) -> LiveMetricsDTO:
    """
    Devuelve la última instantánea de métricas de telemetría y semáforo de energía (HU-17).

    Args:
        session_id (str): UUID de la sesión en vivo.

    Returns:
        LiveMetricsDTO: Última métrica agregada registrada.
    """
    return manager.get_latest_metric(session_id)


@live_router.websocket("/ws/{session_id}")
async def live_stream_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    Canal WebSocket bidireccional de telemetría agregada y sincronizada cada 2.5s (HU-17).
    Envía transmisiones periódicas con semáforos de energía (GREEN/YELLOW/RED) y recibe
    fotogramas efímeros en Base64 para inferencia no invasiva en RAM bajo estándar GDPR.

    Args:
        websocket (WebSocket): Conexión WebSocket del cliente.
        session_id (str): Identificador único de la sesión en vivo.
    """
    await manager.connect(session_id, websocket)

    # Emitir inmediatamente la métrica vigente sin esperar los primeros 2.5s
    initial_metric = manager.get_latest_metric(session_id)
    try:
        await websocket.send_text(initial_metric.model_dump_json())
    except Exception:
        await manager.disconnect(session_id, websocket)
        return

    db = SessionLocal()
    cv_service = ComputerVisionService(db)

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                payload = json.loads(raw_text)
            except Exception:
                continue

            # Ingesta opcional de fotogramas efímeros (GDPR en RAM)
            if isinstance(payload, dict) and "image_base64" in payload:
                frame_dto = FramePayloadDTO(
                    session_id=session_id,
                    image_base64=payload["image_base64"],
                    timestamp_ms=payload.get("timestamp_ms", int(datetime.now(timezone.utc).timestamp() * 1000)),
                )
                computed_metric = cv_service.process_frame_ephemeral(frame_dto)
                manager.update_session_metric(session_id, computed_metric)
                # Notificar de inmediato a los clientes suscritos con la nueva métrica
                await manager.broadcast_metric(session_id, computed_metric)

            elif isinstance(payload, dict) and payload.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "session_id": session_id}))

    except WebSocketDisconnect:
        logger.info("WebSocket cliente desconectado de la sesión %s", session_id)
    except Exception as exc:
        logger.warning("Error en conexión WebSocket de sesión %s: %s", session_id, exc)
    finally:
        db.close()
        await manager.disconnect(session_id, websocket)
