"""
Vinculación de tablets y celulares como monitor de telemetría en vivo (HU-17).

La app móvil solo admite cuentas ATTENDEE, por eso el anfitrión no inicia sesión en ella: desde la
consola web genera un código corto y de un solo uso, y el dispositivo lo canjea por un token de
monitor. Ese token solo permite leer la telemetría de esa sesión; se firma con una clave derivada y
otra audiencia, de modo que el resto de la API lo rechaza.

Los códigos pendientes viven en memoria del proceso (no se persisten), igual que el estado del canal.
"""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings

# Alfabeto sin caracteres ambiguos (sin 0/O, 1/I/L) para dictar o tipear el código
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 6

# Tiempo para canjear un código y duración del token de monitor resultante
CODE_TTL_SECONDS = 15 * 60
MONITOR_TOKEN_TTL = timedelta(hours=8)

# Límite de intentos fallidos de canje por cliente dentro de la ventana
MAX_FAILED_ATTEMPTS = 10
FAILED_ATTEMPTS_WINDOW_SECONDS = 5 * 60

MONITOR_SCOPE = "telemetry:monitor"
MONITOR_AUDIENCE = "experiencia-telemetry-monitor"


class MonitorPairingError(Exception):
    """Error de canje de un código de monitor (inválido, vencido o demasiados intentos)."""

    def __init__(self, detail: str, too_many_attempts: bool = False) -> None:
        """
        Inicializa el error.

        Args:
            detail (str): Mensaje para el cliente.
            too_many_attempts (bool): True si el cliente superó el límite de intentos.
        """
        super().__init__(detail)
        self.detail = detail
        self.too_many_attempts = too_many_attempts


@dataclass(frozen=True)
class MonitorClaims:
    """Datos verificados de un token de monitor."""

    session_id: str
    host_id: str


@dataclass(frozen=True)
class PendingCode:
    """Código emitido que aún no se canjea."""

    session_id: str
    host_id: str
    expires_at: float


def _monitor_signing_key() -> str:
    """
    Deriva la clave de firma de los tokens de monitor a partir del secreto JWT principal.

    Returns:
        str: Clave hexadecimal distinta de `JWT_SECRET`, de modo que los tokens no son intercambiables.
    """
    return sha256(f"{settings.JWT_SECRET}|{MONITOR_AUDIENCE}".encode()).hexdigest()


def create_monitor_token(
    session_id: str, host_id: str, now: datetime | None = None
) -> tuple[str, datetime]:
    """
    Emite un token de monitor de solo lectura para una sesión en vivo.

    Args:
        session_id (str): UUID de la sesión en vivo.
        host_id (str): UUID del anfitrión que autorizó la vinculación.
        now (datetime | None): Instante de emisión (inyectable para pruebas).

    Returns:
        tuple[str, datetime]: Token firmado y su fecha de expiración en UTC.
    """
    issued = now or datetime.now(timezone.utc)
    expires_at = issued + MONITOR_TOKEN_TTL
    claims: dict[str, Any] = {
        "sub": host_id,
        "sid": session_id,
        "scope": MONITOR_SCOPE,
        "aud": MONITOR_AUDIENCE,
        "iat": issued,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, _monitor_signing_key(), algorithm=settings.ALGORITHM), expires_at


def decode_monitor_token(token: str) -> MonitorClaims | None:
    """
    Verifica un token de monitor.

    Args:
        token (str): Token recibido por el canal WebSocket.

    Returns:
        MonitorClaims | None: Sesión y anfitrión del token, o None si no es un token de monitor válido.
    """
    try:
        payload = jwt.decode(
            token,
            _monitor_signing_key(),
            algorithms=[settings.ALGORITHM],
            audience=MONITOR_AUDIENCE,
            options={"require_exp": True, "require_sub": True},
        )
    except JWTError:
        return None
    if payload.get("scope") != MONITOR_SCOPE or not payload.get("sid"):
        return None
    return MonitorClaims(session_id=str(payload["sid"]), host_id=str(payload["sub"]))


def monitor_token_expiry(token: str) -> datetime | None:
    """
    Obtiene la expiración de un token de monitor válido (HU-18: hasta cuándo enviar push al dispositivo).

    Args:
        token (str): Token de monitor.

    Returns:
        datetime | None: Expiración en UTC, o None si el token no es un token de monitor válido.
    """
    if decode_monitor_token(token) is None:
        return None
    claims = jwt.get_unverified_claims(token)
    return datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)


class MonitorPairingService:
    """Emite y canjea códigos de vinculación de un solo uso (HU-17)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """
        Inicializa el almacén en memoria de códigos e intentos.

        Args:
            clock (Callable[[], float]): Reloj monotónico inyectable para pruebas.
        """
        self._clock = clock
        self._codes: dict[str, PendingCode] = {}
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def issue_code(self, session_id: str, host_id: str) -> tuple[str, int]:
        """
        Genera un código nuevo para vincular un dispositivo a la sesión.

        Args:
            session_id (str): UUID de la sesión en vivo ya autorizada.
            host_id (str): UUID del anfitrión que solicita el código.

        Returns:
            tuple[str, int]: Código de 6 caracteres y segundos de validez.
        """
        with self._lock:
            self._purge_expired()
            code = self._new_code()
            self._codes[code] = PendingCode(session_id, host_id, self._clock() + CODE_TTL_SECONDS)
        return code, CODE_TTL_SECONDS

    def redeem(self, code: str, client_key: str) -> MonitorClaims:
        """
        Canjea un código una sola vez.

        Args:
            code (str): Código ingresado en el dispositivo (sin distinguir mayúsculas ni espacios).
            client_key (str): Identificador del cliente para limitar intentos (por ejemplo su IP).

        Returns:
            MonitorClaims: Sesión y anfitrión asociados al código.

        Raises:
            MonitorPairingError: Si el código no existe, venció o el cliente superó los intentos.
        """
        normalized = "".join(code.split()).upper()
        with self._lock:
            self._purge_expired()
            now = self._clock()
            recent = [
                t
                for t in self._failures.get(client_key, [])
                if now - t < FAILED_ATTEMPTS_WINDOW_SECONDS
            ]
            if len(recent) >= MAX_FAILED_ATTEMPTS:
                self._failures[client_key] = recent
                raise MonitorPairingError(
                    "Demasiados intentos. Espera unos minutos.", too_many_attempts=True
                )

            pending = self._codes.pop(normalized, None)
            if pending is None or pending.expires_at < now:
                recent.append(now)
                self._failures[client_key] = recent
                raise MonitorPairingError("Código inválido o vencido.")

            self._failures.pop(client_key, None)
            return MonitorClaims(session_id=pending.session_id, host_id=pending.host_id)

    def _new_code(self) -> str:
        """
        Genera un código aleatorio criptográficamente seguro que no esté en uso.

        Returns:
            str: Código de 6 caracteres del alfabeto sin ambigüedades.
        """
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self._codes:
                return code

    def _purge_expired(self) -> None:
        """Elimina códigos vencidos e intentos antiguos para que el almacén en memoria no crezca."""
        now = self._clock()
        for code in [c for c, pending in self._codes.items() if pending.expires_at < now]:
            del self._codes[code]
        for key in [
            k
            for k, times in self._failures.items()
            if all(now - t >= FAILED_ATTEMPTS_WINDOW_SECONDS for t in times)
        ]:
            del self._failures[key]


# Instancia compartida por el proceso de la API
monitor_pairing_service = MonitorPairingService()


def get_monitor_pairing_service() -> MonitorPairingService:
    """
    Dependencia de FastAPI que entrega el servicio de vinculación del proceso.

    Returns:
        MonitorPairingService: Instancia compartida.
    """
    return monitor_pairing_service
