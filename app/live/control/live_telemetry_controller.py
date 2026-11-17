from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.auth.entity.user import User
from app.core.database import SessionLocal, get_db
from app.core.security import get_current_active_user
from app.live.dto.live_telemetry_dto import LiveTelemetrySnapshotDTO
from app.live.service.live_telemetry_access import (
    TelemetryAccessError,
    authenticate_ws_token,
    authorize_console_viewer,
)
from app.live.service.live_telemetry_service import LiveTelemetryHub, get_live_telemetry_hub

logger = logging.getLogger(__name__)

live_telemetry_router = APIRouter(
    prefix="/live/telemetry",
    tags=["Live Telemetry Console (CU-09 / HU-17)"],
)


@live_telemetry_router.get(
    "/sessions/{session_id}",
    response_model=LiveTelemetrySnapshotDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar la telemetría agregada vigente de una sesión en vivo (HU-17)",
    description=(
        "Devuelve el semáforo de energía suavizado (`GREEN`/`YELLOW`/`RED`), la tendencia, el estado de "
        "la señal y los últimos 60 s de pulso. Es la misma instantánea que emite el WebSocket cada 2.5 s; "
        "sirve como carga inicial o respaldo si el WebSocket no está disponible. Solo el anfitrión "
        "propietario de la sesión o un administrador pueden consultarla."
    ),
)
async def get_live_telemetry(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    hub: Annotated[LiveTelemetryHub, Depends(get_live_telemetry_hub)],
) -> LiveTelemetrySnapshotDTO:
    """
    Consulta la instantánea de telemetría vigente de una sesión del anfitrión autenticado (HU-17).

    Args:
        session_id (str): ID (UUID) de la sesión en vivo.
        current_user (User): Usuario autenticado y activo.
        db (Session): Sesión de base de datos para validar la propiedad de la sesión.
        hub (LiveTelemetryHub): Orquestador de telemetría del proceso.

    Returns:
        LiveTelemetrySnapshotDTO: Semáforo, tendencia, últimos valores y puntos de pulso.

    Raises:
        HTTPException (401): Si no se envía un JWT válido.
        HTTPException (403): Si el usuario no es anfitrión o la sesión es de otro anfitrión.
        HTTPException (404): Si la sesión en vivo no existe.
        HTTPException (422): Si el ID no es un UUID válido.
    """
    try:
        canonical_id = await asyncio.to_thread(authorize_console_viewer, db, session_id, current_user)
    except TelemetryAccessError as exc:
        raise exc.to_http_exception() from exc
    return await hub.get_snapshot(canonical_id)


def _authorize_websocket(session_id: str, token: str | None) -> str:
    """
    Autentica y autoriza a un cliente WebSocket usando una sesión de BD de corta duración.

    Args:
        session_id (str): ID de la sesión en vivo recibido en la ruta.
        token (str | None): JWT enviado en la query.

    Returns:
        str: UUID canónico de la sesión autorizada.

    Raises:
        TelemetryAccessError: Si el token o el permiso sobre la sesión no son válidos.
    """
    with SessionLocal() as db:
        user = authenticate_ws_token(db, token)
        return authorize_console_viewer(db, session_id, user)


@live_telemetry_router.websocket("/ws/{session_id}")
async def live_telemetry_websocket(
    websocket: WebSocket,
    session_id: str,
    hub: Annotated[LiveTelemetryHub, Depends(get_live_telemetry_hub)],
    token: Annotated[str | None, Query(description="JWT de acceso del anfitrión")] = None,
) -> None:
    """
    Canal WebSocket de solo lectura que emite la telemetría agregada cada 2.5 s (HU-17).

    Conexión: `ws://<host>/api/live/telemetry/ws/{session_id}?token=<JWT>`. Al conectarse, el cliente
    recibe de inmediato la instantánea vigente y luego una cada 2.5 s, sincronizada para todos los
    clientes de la sesión. El cliente puede enviar `{"type": "ping"}` y recibe `{"type": "pong"}`.
    Si la autorización falla, el canal se cierra con 4401 (token), 4403 (permiso) o 4404 (sesión).

    Args:
        websocket (WebSocket): Conexión WebSocket del cliente.
        session_id (str): ID (UUID) de la sesión en vivo.
        hub (LiveTelemetryHub): Orquestador de telemetría del proceso.
        token (str | None): JWT de acceso del anfitrión.
    """
    await websocket.accept()
    try:
        canonical_id = await asyncio.to_thread(_authorize_websocket, session_id, token)
    except TelemetryAccessError as exc:
        await websocket.close(code=exc.ws_close_code, reason=exc.detail)
        return

    await hub.subscribe(canonical_id, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except ValueError:
                continue
            if isinstance(payload, dict) and payload.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "session_id": canonical_id}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("Conexión de consola cerrada por error en la sesión %s: %s", canonical_id, exc)
    finally:
        await hub.unsubscribe(canonical_id, websocket)
