from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.auth.repository.user_repository import UserRepository
from app.core.config import settings
from app.core.database import get_db

# Esquema de autenticación Bearer para Swagger UI y clientes HTTP
http_bearer = HTTPBearer(auto_error=False)
oauth2_scheme = http_bearer  # Alias de compatibilidad

# Registro en memoria de tokens JWT revocados mediante Logout (CU-02)
_revoked_tokens: set[str] = set()


def normalize_bearer_token(token: str) -> str:
    """
    Normaliza una cadena de token JWT eliminando el prefijo 'Bearer ' y espacios circundantes.

    Args:
        token (str): Token JWT bruto recibido desde cabeceras HTTP o cuerpo de petición.

    Returns:
        str: Token JWT limpio listo para decodificación o revocación.
    """
    clean_token = str(token).strip()
    if clean_token.lower().startswith("bearer "):
        clean_token = clean_token[7:].strip()
    return clean_token


def revoke_token(token: str) -> None:
    """
    Revoca e invalida un token JWT activo agregándolo a la lista negra de sesión cerrada (CU-02 Logout).

    Args:
        token (str): Token JWT que se desea invalidar.
    """
    clean_token = normalize_bearer_token(token)
    if clean_token:
        _revoked_tokens.add(clean_token)


def is_token_revoked(token: str) -> bool:
    """
    Verifica si un token JWT ha sido revocado previamente mediante cierre de sesión (Logout).

    Args:
        token (str): Token JWT a consultar.

    Returns:
        bool: `True` si el token fue revocado, `False` en caso contrario.
    """
    return normalize_bearer_token(token) in _revoked_tokens


def clear_revoked_tokens() -> None:
    """
    Limpia el registro en memoria de tokens revocados (útil al reiniciar la base de datos en pruebas).
    """
    _revoked_tokens.clear()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica criptográficamente si una contraseña en texto plano coincide con su hash bcrypt (CU-01, CU-02).

    Args:
        plain_password (str): Contraseña en texto plano ingresada por el usuario.
        hashed_password (str): Hash bcrypt almacenado en la base de datos.

    Returns:
        bool: `True` si la contraseña coincide exactamente, `False` en caso contrario.
    """
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """
    Genera un hash seguro con sal aleatoria utilizando el algoritmo bcrypt (CU-01).

    Args:
        password (str): Contraseña en texto plano a encriptar.

    Returns:
        str: Hash bcrypt codificado en UTF-8.
    """
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Crea un token de acceso JWT firmado digitalmente con HS256, incluyendo identificador único `jti`
    y marca de tiempo de expiración `exp` en UTC (CU-02).

    Args:
        subject (str | int): Identificador del usuario propietario del token (`sub`).
        expires_delta (timedelta | None): Duración personalizada opcional de validez del token.

    Returns:
        str: Token JWT firmado y codificado.
    """
    now = datetime.now(timezone.utc)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)

    to_encode: dict[str, Any] = {
        "exp": expire,
        "iat": now,
        "sub": str(subject),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decodifica y valida la firma criptográfica, vigencia temporal y estado de revocación de un token JWT.

    Args:
        token (str): Token JWT con o sin prefijo `Bearer `.

    Returns:
        dict[str, Any]: Payload decodificado del token JWT (`sub`, `exp`, `iat`, `jti`).

    Raises:
        HTTPException (401): Si el token fue revocado por logout, es inválido o ha expirado.
    """
    clean_token = normalize_bearer_token(token)
    if is_token_revoked(clean_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revocado. La sesión ha sido cerrada (Logout).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload: dict[str, Any] = jwt.decode(
            clean_token,
            settings.JWT_SECRET,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_token(
    auth: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)] = None,
) -> str:
    """
    Dependencia de FastAPI que extrae y normaliza el token JWT Bearer de la cabecera `Authorization`.

    Args:
        auth (HTTPAuthorizationCredentials | None): Credenciales extraídas por `HTTPBearer`.

    Returns:
        str: Token JWT limpio.

    Raises:
        HTTPException (401): Si no se proporcionó la cabecera `Authorization: Bearer <token>`.
    """
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se proporcionó token de autenticación (Header 'Authorization: Bearer <token>' requerido)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return normalize_bearer_token(auth.credentials)


def get_current_user(
    auth: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)] = None,
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
) -> User:
    """
    Dependencia de FastAPI que extrae, valida y recupera la entidad `User` autenticada a partir del JWT Bearer.

    Args:
        auth (HTTPAuthorizationCredentials | None): Credenciales HTTP Bearer inyectadas por FastAPI.
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        User: Instancia ORM del usuario autenticado.

    Raises:
        HTTPException (401): Si el token falta, es inválido, fue revocado o el usuario no existe.
    """
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se proporcionó token de autenticación (Header 'Authorization: Bearer <token>' requerido)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_str = normalize_bearer_token(auth.credentials)
    payload = decode_token(token_str)
    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no contiene identificador de usuario válido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(user_id_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identificador de usuario no es numérico",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_repo = UserRepository(db)
    user = user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado en la base de datos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Dependencia de FastAPI que verifica que el usuario autenticado tenga su cuenta activa (`is_active=True`).

    Args:
        current_user (User): Usuario autenticado resuelto por `get_current_user`.

    Returns:
        User: Usuario activo verificado.

    Raises:
        HTTPException (403): Si la cuenta de usuario se encuentra desactivada o suspendida.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta de usuario está desactivada o suspendida",
        )
    return current_user


class RoleChecker:
    """
    Dependencia parametrizable de FastAPI para Control de Acceso Basado en Roles (RBAC).
    Verifica que el usuario autenticado posea al menos uno de los roles autorizados.
    """

    def __init__(self, allowed_roles: list[str]) -> None:
        """
        Inicializa el verificador de roles permitidos.

        Args:
            allowed_roles (list[str]): Lista de nombres de roles autorizados (ej. `["HOST", "VENUE", "ADMIN"]`).
        """
        self.allowed_roles: list[str] = [r.upper().strip() for r in allowed_roles]

    def __call__(
        self,
        current_user: Annotated[User, Depends(get_current_active_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> User:
        """
        Evalúa los roles asignados al usuario activo frente a la lista de roles permitidos.

        Args:
            current_user (User): Usuario activo autenticado.
            db (Session): Sesión activa de base de datos.

        Returns:
            User: El usuario autenticado si cuenta con permisos suficientes.

        Raises:
            HTTPException (403): Si el usuario no posee ninguno de los roles requeridos.
        """
        user_repo = UserRepository(db)
        user_roles = user_repo.get_user_roles(current_user.id)
        if not any(role in self.allowed_roles for role in user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permisos insuficientes. Requiere uno de los siguientes roles: {self.allowed_roles}",
            )
        return current_user
