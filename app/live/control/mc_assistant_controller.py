from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.entity.user import User
from app.auth.repository.user_repository import UserRepository
from app.core.database import SessionLocal
from app.core.security import get_current_active_user, get_current_token
from app.live.dto.mc_assistant_dto import (
    McAlertDTO,
    McDynamicDTO,
    PushDeviceRegisterDTO,
    PushDeviceRegisteredDTO,
)
from app.live.service.live_monitor_pairing import decode_monitor_token, monitor_token_expiry
from app.live.service.live_telemetry_access import (
    CONSOLE_ROLES,
    SessionActor,
    TelemetryAccessError,
    authorize_session_actor,
)
from app.live.service.mc_assistant_service import McAssistantService, get_mc_assistant_service

mc_assistant_router = APIRouter(
    prefix="/mc",
    tags=["Live MC Assistant (CU-11 / HU-18, HU-19)"],
)


def _authorize(session_id: str, token: str) -> SessionActor:
    """
    Autoriza al anfitrión (JWT) o al monitor vinculado (token de monitor) sobre la sesión.

    Args:
        session_id (str): ID de la sesión en vivo.
        token (str): Token Bearer recibido.

    Returns:
        SessionActor: Sesión autorizada y tipo de actor.

    Raises:
        HTTPException (401/403/404/422): Según el motivo del rechazo.
    """
    with SessionLocal() as db:
        try:
            return authorize_session_actor(db, session_id, token)
        except TelemetryAccessError as exc:
            raise exc.to_http_exception() from exc


async def _authorize_alert(alert_id: str, token: str, service: McAssistantService) -> None:
    """
    Verifica que la alerta exista y que el actor administre su sesión.

    Args:
        alert_id (str): UUID de la alerta.
        token (str): Token Bearer recibido.
        service (McAssistantService): Asistente MC del proceso.

    Raises:
        HTTPException (404): Si la alerta no existe o el ID no es válido.
        HTTPException (401/403): Si el actor no puede administrar la sesión.
    """
    try:
        session_id = await asyncio.to_thread(service.store.get_alert_session, alert_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada"
        ) from exc
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada")
    await asyncio.to_thread(_authorize, session_id, token)


@mc_assistant_router.get(
    "/dynamics",
    response_model=list[McDynamicDTO],
    summary="Consultar el catálogo de dinámicas del Asistente MC (HU-19)",
    description="Devuelve las dinámicas activas con textos en español e inglés. Requiere rol de anfitrión.",
)
async def list_mc_dynamics(
    current_user: Annotated[User, Depends(get_current_active_user)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> list[McDynamicDTO]:
    """
    Lista el catálogo de dinámicas del Asistente MC (HU-19).

    Args:
        current_user (User): Usuario autenticado y activo.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        list[McDynamicDTO]: Dinámicas activas.

    Raises:
        HTTPException (403): Si el usuario no tiene rol de anfitrión.
    """
    with SessionLocal() as db:
        roles = set(UserRepository(db).get_user_roles(str(current_user.id)))
    if not roles & CONSOLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requiere rol de anfitrión"
        )
    return await asyncio.to_thread(service.store.list_dynamics)


@mc_assistant_router.get(
    "/sessions/{session_id}/alerts",
    response_model=list[McAlertDTO],
    summary="Consultar el historial de alertas del Asistente MC de una sesión (HU-18)",
    description="Acepta el JWT del anfitrión propietario, de un administrador o el token del monitor vinculado.",
)
async def list_mc_alerts(
    session_id: str,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> list[McAlertDTO]:
    """
    Lista las alertas de la sesión, de la más reciente a la más antigua (HU-18).

    Args:
        session_id (str): ID (UUID) de la sesión en vivo.
        token (str): JWT del anfitrión o token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        list[McAlertDTO]: Historial de alertas.
    """
    actor = await asyncio.to_thread(_authorize, session_id, token)
    return await asyncio.to_thread(service.store.list_alerts, actor.session_id)


@mc_assistant_router.post(
    "/sessions/{session_id}/request",
    response_model=McAlertDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Pedir una dinámica al Asistente MC sin esperar la alerta (HU-19)",
    description="Crea una alerta manual con una dinámica sugerida; si ya hay una activa, la devuelve.",
)
async def request_mc_dynamic(
    session_id: str,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> McAlertDTO:
    """
    Crea una alerta manual con una dinámica sugerida (HU-19).

    Args:
        session_id (str): ID (UUID) de la sesión en vivo.
        token (str): JWT del anfitrión o token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        McAlertDTO: Alerta activa con su dinámica.
    """
    actor = await asyncio.to_thread(_authorize, session_id, token)
    return await service.request_dynamic(actor.session_id)


@mc_assistant_router.post(
    "/alerts/{alert_id}/apply",
    response_model=McAlertDTO,
    summary="Aplicar la dinámica sugerida (HU-19)",
    description="Marca la dinámica como aplicada. Si es una pausa, fija `break_ends_at` y suspende alertas hasta el regreso.",
)
async def apply_mc_alert(
    alert_id: str,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> McAlertDTO:
    """
    Aplica la dinámica de una alerta activa (HU-19).

    Args:
        alert_id (str): UUID de la alerta.
        token (str): JWT del anfitrión o token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        McAlertDTO: Alerta aplicada.

    Raises:
        HTTPException (409): Si la alerta ya fue atendida.
    """
    await _authorize_alert(alert_id, token, service)
    return await service.apply(alert_id)


@mc_assistant_router.post(
    "/alerts/{alert_id}/dismiss",
    response_model=McAlertDTO,
    summary="Descartar la dinámica sugerida (HU-18)",
)
async def dismiss_mc_alert(
    alert_id: str,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> McAlertDTO:
    """
    Descarta una alerta activa sin aplicar la dinámica (HU-18).

    Args:
        alert_id (str): UUID de la alerta.
        token (str): JWT del anfitrión o token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        McAlertDTO: Alerta descartada.
    """
    await _authorize_alert(alert_id, token, service)
    return await service.dismiss(alert_id)


@mc_assistant_router.post(
    "/alerts/{alert_id}/next",
    response_model=McAlertDTO,
    summary="Proponer otra dinámica para la alerta activa (HU-19)",
)
async def next_mc_dynamic(
    alert_id: str,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> McAlertDTO:
    """
    Cambia la dinámica sugerida de una alerta activa (HU-19).

    Args:
        alert_id (str): UUID de la alerta.
        token (str): JWT del anfitrión o token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        McAlertDTO: Alerta con otra dinámica.
    """
    await _authorize_alert(alert_id, token, service)
    return await service.next_dynamic(alert_id)


@mc_assistant_router.post(
    "/monitor/push-device",
    response_model=PushDeviceRegisteredDTO,
    summary="Registrar el celular vinculado para recibir alertas push (HU-18)",
    description=(
        "Solo acepta el token de monitor obtenido al vincular el dispositivo. El registro dura lo mismo "
        "que el token de monitor y mantiene activa la evaluación de la sesión aunque la app esté cerrada."
    ),
)
async def register_monitor_push_device(
    dto: PushDeviceRegisterDTO,
    token: Annotated[str, Depends(get_current_token)],
    service: Annotated[McAssistantService, Depends(get_mc_assistant_service)],
) -> PushDeviceRegisteredDTO:
    """
    Registra el token de Firebase del monitor vinculado (HU-18).

    Args:
        dto (PushDeviceRegisterDTO): Token de Firebase, plataforma e idioma.
        token (str): Token de monitor.
        service (McAssistantService): Asistente MC del proceso.

    Returns:
        PushDeviceRegisteredDTO: Resultado del registro.

    Raises:
        HTTPException (401): Si el token no es un token de monitor válido.
    """
    claims = decode_monitor_token(token)
    expires_at = monitor_token_expiry(token)
    if claims is None or expires_at is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Requiere el token del monitor vinculado",
        )
    actor = await asyncio.to_thread(_authorize, claims.session_id, token)
    return await service.register_push_device(
        actor.session_id, dto.fcm_token, dto.platform, dto.language, expires_at
    )
