from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.orm import Session

from app.auth.entity.user import User
from app.core.database import SessionLocal, get_db
from app.core.security import get_current_active_user
from app.experience.entity.experience import Experience
from app.live.dto.live_telemetry_dto import (
    LiveTelemetrySnapshotDTO,
    MonitorCodeDTO,
    MonitorRedeemDTO,
    MonitorTokenDTO,
)
from app.live.repository.live_telemetry_repository import LiveTelemetryRepository
from app.live.service.live_monitor_pairing import (
    MonitorPairingError,
    MonitorPairingService,
    create_monitor_token,
    decode_monitor_token,
    get_monitor_pairing_service,
)
from app.live.service.live_telemetry_access import (
    TelemetryAccessError,
    authenticate_ws_token,
    authorize_console_viewer,
    authorize_monitor,
)
from app.live.service.live_telemetry_service import LiveTelemetryHub, get_live_telemetry_hub

logger = logging.getLogger(__name__)

live_telemetry_router = APIRouter(
    prefix="/live",
    tags=["Live Telemetry Console (CU-09 / HU-17)"],
)


@live_telemetry_router.get(
    "/telemetry/sessions/{session_id}",
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
        canonical_id = await asyncio.to_thread(
            authorize_console_viewer, db, session_id, current_user
        )
    except TelemetryAccessError as exc:
        raise exc.to_http_exception() from exc
    return await hub.get_snapshot(canonical_id)


@live_telemetry_router.post(
    "/telemetry/sessions/{session_id}/monitor-code",
    response_model=MonitorCodeDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Generar un código para vincular una tablet o celular como monitor (HU-17)",
    description=(
        "Emite un código de 6 caracteres, de un solo uso y válido por 15 minutos. La app móvil lo canjea "
        "en `/live/telemetry/monitor/redeem` para ver el semáforo de esta sesión sin iniciar sesión como "
        "anfitrión (la app móvil solo admite cuentas ATTENDEE). Solo el anfitrión propietario o un "
        "administrador pueden generarlo."
    ),
)
async def create_monitor_code(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
    pairing: Annotated[MonitorPairingService, Depends(get_monitor_pairing_service)],
) -> MonitorCodeDTO:
    """
    Genera un código de vinculación de monitor para una sesión del anfitrión autenticado (HU-17).

    Args:
        session_id (str): ID (UUID) de la sesión en vivo.
        current_user (User): Usuario autenticado y activo.
        db (Session): Sesión de base de datos para validar la propiedad de la sesión.
        pairing (MonitorPairingService): Servicio de códigos de vinculación del proceso.

    Returns:
        MonitorCodeDTO: Código y segundos de validez.

    Raises:
        HTTPException (401/403/404/422): Mismas reglas de acceso que la consola.
    """
    try:
        canonical_id = await asyncio.to_thread(
            authorize_console_viewer, db, session_id, current_user
        )
    except TelemetryAccessError as exc:
        raise exc.to_http_exception() from exc
    live_session = LiveTelemetryRepository(db).get_session(canonical_id)
    if live_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sesión en vivo no encontrada"
        )
    code, ttl = pairing.issue_code(canonical_id, str(live_session.host_id))
    return MonitorCodeDTO(code=code, session_id=canonical_id, expires_in_seconds=ttl)


@live_telemetry_router.post(
    "/telemetry/monitor/redeem",
    response_model=MonitorTokenDTO,
    status_code=status.HTTP_200_OK,
    summary="Canjear un código de monitor por un token de solo lectura (HU-17)",
    description=(
        "No requiere iniciar sesión. Devuelve un token válido por 8 horas que solo permite conectarse al "
        "WebSocket de telemetría de la sesión vinculada; cualquier otro endpoint lo rechaza. Tras 10 "
        "intentos fallidos en 5 minutos responde 429."
    ),
)
def redeem_monitor_code(
    dto: MonitorRedeemDTO,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    pairing: Annotated[MonitorPairingService, Depends(get_monitor_pairing_service)],
) -> MonitorTokenDTO:
    """
    Canjea un código de vinculación por un token de monitor (HU-17).

    Args:
        dto (MonitorRedeemDTO): Código ingresado en el dispositivo.
        request (Request): Petición HTTP, usada para limitar intentos por IP.
        db (Session): Sesión de base de datos para leer el título de la experiencia.
        pairing (MonitorPairingService): Servicio de códigos de vinculación del proceso.

    Returns:
        MonitorTokenDTO: Token de monitor, sesión vinculada y título de la experiencia.

    Raises:
        HTTPException (400): Si el código es inválido, ya se usó o venció.
        HTTPException (429): Si el cliente superó el límite de intentos fallidos.
    """
    client_key = request.client.host if request.client else "unknown"
    try:
        claims = pairing.redeem(dto.code, client_key)
    except MonitorPairingError as exc:
        code = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if exc.too_many_attempts
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=exc.detail) from exc

    live_session = LiveTelemetryRepository(db).get_session(claims.session_id)
    experience = db.get(Experience, live_session.experience_id) if live_session else None
    if live_session is None or experience is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La sesión en vivo ya no está disponible.",
        )

    token, expires_at = create_monitor_token(claims.session_id, claims.host_id)
    return MonitorTokenDTO(
        access_token=token,
        session_id=claims.session_id,
        experience_title=str(experience.title),
        expires_at=expires_at,
    )


def _authorize_websocket(session_id: str, token: str | None) -> str:
    """
    Autentica y autoriza a un cliente WebSocket usando una sesión de BD de corta duración.

    Acepta el JWT del anfitrión (consola web) o un token de monitor (tablet o celular vinculado).

    Args:
        session_id (str): ID de la sesión en vivo recibido en la ruta.
        token (str | None): JWT o token de monitor enviado en la query.

    Returns:
        str: UUID canónico de la sesión autorizada.

    Raises:
        TelemetryAccessError: Si el token o el permiso sobre la sesión no son válidos.
    """
    with SessionLocal() as db:
        monitor_claims = decode_monitor_token(token) if token else None
        if monitor_claims is not None:
            return authorize_monitor(db, session_id, monitor_claims)
        user = authenticate_ws_token(db, token)
        return authorize_console_viewer(db, session_id, user)


@live_telemetry_router.websocket("/telemetry/ws/{session_id}")
async def live_telemetry_websocket(
    websocket: WebSocket,
    session_id: str,
    hub: Annotated[LiveTelemetryHub, Depends(get_live_telemetry_hub)],
    token: Annotated[
        str | None, Query(description="JWT del anfitrión o token de monitor vinculado")
    ] = None,
) -> None:
    """
    Canal WebSocket de solo lectura que emite la telemetría agregada cada 2.5 s (HU-17).

    Conexión: `ws://<host>/api/live/telemetry/ws/{session_id}?token=<JWT o token de monitor>`. Al conectarse, el cliente
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
        logger.warning(
            "Conexión de consola cerrada por error en la sesión %s: %s", canonical_id, exc
        )
    finally:
        await hub.unsubscribe(canonical_id, websocket)


# HU-18/HU-19: el Asistente MC se publica bajo este mismo router para no modificar main.py
from app.live.control.mc_assistant_controller import mc_assistant_router  # noqa: E402

live_telemetry_router.include_router(mc_assistant_router)
