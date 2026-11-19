"""
Control de acceso a la consola de telemetría en vivo (HU-17).

Solo el anfitrión propietario de la sesión, o un administrador, puede observar su telemetría.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth.entity.user import User
from app.auth.repository.user_repository import UserRepository
from app.booking.service.booking_service import uuid_string
from app.core.security import decode_token
from app.live.repository.live_telemetry_repository import LiveTelemetryRepository
from app.live.service.live_monitor_pairing import MonitorClaims, decode_monitor_token

# Roles con acceso a la consola (VENUE se mantiene por compatibilidad, igual que HU-16)
CONSOLE_ROLES = frozenset({"HOST", "VENUE", "ADMIN"})

# Códigos de cierre WebSocket de aplicación (rango 4000-4999 del RFC 6455)
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_FORBIDDEN = 4403
WS_CLOSE_NOT_FOUND = 4404


@dataclass(frozen=True)
class TelemetryAccessError(Exception):
    """Error de autorización de la consola con su código HTTP y su código de cierre WebSocket."""

    http_status: int
    ws_close_code: int
    detail: str

    def to_http_exception(self) -> HTTPException:
        """
        Convierte el error en una excepción HTTP de FastAPI.

        Returns:
            HTTPException: Excepción con el estado y el detalle del error.
        """
        return HTTPException(status_code=self.http_status, detail=self.detail)


def authorize_console_viewer(db: Session, session_id: str, user: User) -> str:
    """
    Verifica que el usuario pueda observar la telemetría de la sesión en vivo.

    Args:
        db (Session): Sesión de base de datos.
        session_id (str): ID de la sesión en vivo recibido en la ruta.
        user (User): Usuario autenticado y activo.

    Returns:
        str: UUID canónico de la sesión autorizada.

    Raises:
        TelemetryAccessError: 422 si el ID no es UUID, 404 si la sesión no existe y 403 si el usuario
            no tiene rol de consola o la sesión pertenece a otro anfitrión.
    """
    try:
        canonical_id = uuid_string(session_id)
    except HTTPException as exc:
        raise TelemetryAccessError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, WS_CLOSE_NOT_FOUND, "ID de sesión inválido"
        ) from exc

    roles = set(UserRepository(db).get_user_roles(str(user.id)))
    if not roles & CONSOLE_ROLES:
        raise TelemetryAccessError(
            status.HTTP_403_FORBIDDEN,
            WS_CLOSE_FORBIDDEN,
            "Requiere rol de anfitrión para ver la consola",
        )

    live_session = LiveTelemetryRepository(db).get_session(canonical_id)
    if live_session is None:
        raise TelemetryAccessError(
            status.HTTP_404_NOT_FOUND, WS_CLOSE_NOT_FOUND, "Sesión en vivo no encontrada"
        )

    if "ADMIN" not in roles and str(live_session.host_id) != str(user.id):
        raise TelemetryAccessError(
            status.HTTP_403_FORBIDDEN, WS_CLOSE_FORBIDDEN, "No administras esta sesión en vivo"
        )
    return canonical_id


def authorize_monitor(db: Session, session_id: str, claims: MonitorClaims) -> str:
    """
    Verifica que un token de monitor (tablet o celular vinculado) corresponda a la sesión pedida.

    Args:
        db (Session): Sesión de base de datos.
        session_id (str): ID de la sesión en vivo recibido en la ruta.
        claims (MonitorClaims): Datos verificados del token de monitor.

    Returns:
        str: UUID canónico de la sesión autorizada.

    Raises:
        TelemetryAccessError: 404 si la sesión no existe y 403 si el token es de otra sesión,
            el anfitrión ya no la administra o su cuenta fue desactivada.
    """
    try:
        canonical_id = uuid_string(session_id)
    except HTTPException as exc:
        raise TelemetryAccessError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, WS_CLOSE_NOT_FOUND, "ID de sesión inválido"
        ) from exc

    if claims.session_id != canonical_id:
        raise TelemetryAccessError(
            status.HTTP_403_FORBIDDEN, WS_CLOSE_FORBIDDEN, "El monitor está vinculado a otra sesión"
        )

    live_session = LiveTelemetryRepository(db).get_session(canonical_id)
    if live_session is None:
        raise TelemetryAccessError(
            status.HTTP_404_NOT_FOUND, WS_CLOSE_NOT_FOUND, "Sesión en vivo no encontrada"
        )

    host = UserRepository(db).get_by_id(claims.host_id)
    if str(live_session.host_id) != claims.host_id or host is None or not bool(host.is_active):
        raise TelemetryAccessError(
            status.HTTP_403_FORBIDDEN, WS_CLOSE_FORBIDDEN, "La vinculación ya no es válida"
        )
    return canonical_id


def authenticate_ws_token(db: Session, token: str | None) -> User:
    """
    Autentica al cliente WebSocket con el JWT enviado en la query (`?token=`).

    Los navegadores no permiten cabeceras personalizadas en WebSocket, por eso el token viaja en la URL.

    Args:
        db (Session): Sesión de base de datos.
        token (str | None): JWT de acceso del usuario.

    Returns:
        User: Usuario autenticado y activo.

    Raises:
        TelemetryAccessError: 401 si falta el token, es inválido, fue revocado o el usuario no está activo.
    """
    if not token:
        raise TelemetryAccessError(
            status.HTTP_401_UNAUTHORIZED, WS_CLOSE_UNAUTHORIZED, "Token requerido"
        )
    try:
        payload = decode_token(token, db)
    except HTTPException as exc:
        raise TelemetryAccessError(
            status.HTTP_401_UNAUTHORIZED, WS_CLOSE_UNAUTHORIZED, str(exc.detail)
        ) from exc

    try:
        user_id = uuid_string(str(payload.get("sub", "")).strip())
    except HTTPException as exc:
        raise TelemetryAccessError(
            status.HTTP_401_UNAUTHORIZED, WS_CLOSE_UNAUTHORIZED, "Token sin usuario válido"
        ) from exc

    user = UserRepository(db).get_by_id(user_id)
    if user is None or not bool(user.is_active):
        raise TelemetryAccessError(
            status.HTTP_401_UNAUTHORIZED, WS_CLOSE_UNAUTHORIZED, "Usuario no válido"
        )
    return user


@dataclass(frozen=True)
class SessionActor:
    """Quién actúa sobre una sesión en vivo: el anfitrión (JWT) o un monitor vinculado."""

    session_id: str
    is_monitor: bool


def authorize_session_actor(db: Session, session_id: str, token: str | None) -> SessionActor:
    """
    Autoriza a quien actúa sobre la sesión con el JWT del anfitrión o con un token de monitor (HU-18).

    El celular vinculado no tiene cuenta de anfitrión en la app móvil, por eso puede responder las
    alertas del Asistente MC con su token de monitor, limitado a su propia sesión.

    Args:
        db (Session): Sesión de base de datos.
        session_id (str): ID de la sesión en vivo.
        token (str | None): JWT del anfitrión o token de monitor.

    Returns:
        SessionActor: Sesión autorizada y tipo de actor.

    Raises:
        TelemetryAccessError: Si el token no es válido o no corresponde a la sesión.
    """
    monitor_claims = decode_monitor_token(token) if token else None
    if monitor_claims is not None:
        return SessionActor(authorize_monitor(db, session_id, monitor_claims), is_monitor=True)
    user = authenticate_ws_token(db, token)
    return SessionActor(authorize_console_viewer(db, session_id, user), is_monitor=False)
