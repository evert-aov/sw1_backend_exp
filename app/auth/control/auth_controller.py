from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.auth.dto.auth_dto import (
    LoginDTO,
    LogoutResponseDTO,
    PreferencesUpdateDTO,
    ProfileDTO,
    ProfileUpdateDTO,
    RegisterDTO,
    TokenResponseDTO,
)
from app.auth.entity.user import User
from app.auth.service.auth_service import AuthService
from app.auth.service.profile_service import ProfileService
from app.core.database import get_db
from app.core.security import get_current_active_user, get_current_token

auth_router = APIRouter(prefix="/auth", tags=["Auth Controller (CU-01, CU-02)"])
users_router = APIRouter(prefix="/users", tags=["Users Controller (CU-03)"])


# =====================================================================
# Endpoints de Registro y Autenticación con JWT (CU-01 y CU-02)
# =====================================================================


@auth_router.post(
    "/register",
    response_model=ProfileDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una nueva cuenta de usuario (CU-01 / HU-01)",
    description=(
        "Registra un nuevo usuario en la plataforma validando unicidad de correo electrónico, "
        "encriptando su contraseña con bcrypt y asignándole el rol solicitado (`ATTENDEE`, `HOST`, `VENUE`, `ADMIN`)."
    ),
    response_description="Perfil del usuario creado exitosamente",
)
def register(
    dto: RegisterDTO,
    db: Annotated[Session, Depends(get_db)],
) -> ProfileDTO:
    """
    Endpoint para registrar una nueva cuenta de usuario (CU-01: Registrar Cuenta).

    Args:
        dto (RegisterDTO): Datos personales, credenciales y rol inicial del usuario.
        db (Session): Sesión de base de datos inyectada por FastAPI.

    Returns:
        ProfileDTO: Datos del perfil recién registrado con código HTTP 201.
    """
    service = AuthService(db)
    return service.register(dto)


@auth_router.post(
    "/login",
    response_model=TokenResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Iniciar sesión y obtener token JWT (CU-02 / HU-02)",
    description=(
        "Autentica las credenciales del usuario (`email` y `password`) y emite un token JWT firmado (HS256) "
        "junto con la lista de roles asociados para consumir endpoints protegidos."
    ),
    response_description="Token JWT emitido e información básica de sesión",
)
def login(
    dto: LoginDTO,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponseDTO:
    """
    Endpoint para autenticar un usuario e iniciar sesión con JWT (CU-02: Autenticar Usuario - Login).

    Args:
        dto (LoginDTO): Correo electrónico y contraseña del usuario.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        TokenResponseDTO: Token JWT de acceso, tipo Bearer, ID de usuario, correo y roles.
    """
    service = AuthService(db)
    return service.login(dto)


@auth_router.post(
    "/logout",
    response_model=LogoutResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Cerrar sesión e invalidar token JWT activo (CU-02 / HU-02)",
    description=(
        "Revoca el token JWT Bearer actual del usuario autenticado agregándolo a la lista de tokens "
        "invalidados para impedir su uso en peticiones posteriores."
    ),
    response_description="Confirmación de cierre de sesión y revocación del token JWT",
)
def logout(
    current_user: Annotated[User, Depends(get_current_active_user)],
    token: Annotated[str, Depends(get_current_token)],
    db: Annotated[Session, Depends(get_db)],
) -> LogoutResponseDTO:
    """
    Endpoint para cerrar sesión e invalidar el token JWT activo (CU-02: Autenticar Usuario - Logout).

    Args:
        current_user (User): Usuario activo autenticado.
        token (str): Token JWT Bearer extraído de la cabecera `Authorization`.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        LogoutResponseDTO: Estado de confirmación y marca de tiempo del cierre de sesión.
    """
    service = AuthService(db)
    return service.logout(user=current_user, token=token)


@auth_router.post(
    "/refresh",
    response_model=TokenResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Renovar token JWT de acceso (CU-02 / HU-02)",
    description="Emite un nuevo token JWT con expiración extendida para el usuario autenticado activo.",
    response_description="Nuevo token JWT emitido",
)
def refresh_token(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponseDTO:
    """
    Endpoint para renovar el token JWT de un usuario con sesión activa (CU-02).

    Args:
        current_user (User): Usuario activo autenticado mediante su JWT actual.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        TokenResponseDTO: Nuevo token JWT firmado.
    """
    service = AuthService(db)
    return service.refresh_token_for_user(current_user)


# =====================================================================
# Endpoints de Gestión de Perfil de Usuario y Preferencias (CU-03)
# =====================================================================


@users_router.get(
    "",
    response_model=list[ProfileDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar usuarios registrados (CU-03 / HU-03)",
    description="Consulta de forma paginada la lista de usuarios registrados con sus roles e intereses.",
    response_description="Lista paginada de perfiles de usuario",
)
def list_users(
    skip: Annotated[int, Query(ge=0, description="Número de registros a omitir")] = 0,
    limit: Annotated[int, Query(ge=1, le=500, description="Límite de usuarios por página")] = 100,
    current_user: Annotated[User, Depends(get_current_active_user)] = None,  # type: ignore[assignment]
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
) -> list[ProfileDTO]:
    """
    Lista todos los perfiles de usuario registrados en la plataforma (requiere autenticación JWT).

    Args:
        skip (int): Cantidad de registros a omitir para paginación.
        limit (int): Cantidad máxima de registros a devolver.
        current_user (User): Usuario autenticado que realiza la consulta.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        list[ProfileDTO]: Lista de perfiles de usuario.
    """
    service = ProfileService(db)
    return service.list_users(skip=skip, limit=limit)


@users_router.get(
    "/me",
    response_model=ProfileDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar el perfil del usuario autenticado (CU-03 / HU-03)",
    description="Obtiene los datos personales, avatar, biografía, roles y etiquetas de intereses del usuario actual.",
    response_description="Perfil completo del usuario autenticado",
)
def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfileDTO:
    """
    Consulta y retorna el perfil completo y preferencias del usuario autenticado (CU-03).

    Args:
        current_user (User): Usuario autenticado resuelto desde el token JWT.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        ProfileDTO: Información personal y preferencias del usuario actual.
    """
    service = ProfileService(db)
    return service.get_profile(current_user.id)


@users_router.put(
    "/me",
    response_model=ProfileDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar perfil y preferencias del usuario autenticado (CU-03 / HU-03)",
    description=(
        "Actualiza nombres, apellidos, teléfono, URL de foto de perfil (`avatar_url`), biografía (`bio`) "
        "y lista de etiquetas de intereses temáticos (`interests`) del usuario en sesión."
    ),
    response_description="Perfil de usuario actualizado",
)
def update_current_user_profile(
    dto: ProfileUpdateDTO,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfileDTO:
    """
    Actualiza el perfil personal y las etiquetas de preferencias del usuario autenticado (CU-03).

    Args:
        dto (ProfileUpdateDTO): Datos personales y preferencias a modificar.
        current_user (User): Usuario autenticado en sesión.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        ProfileDTO: Perfil de usuario con los cambios aplicados.
    """
    service = ProfileService(db)
    return service.update_profile(current_user.id, dto)


@users_router.patch(
    "/me/preferences",
    response_model=ProfileDTO,
    status_code=status.HTTP_200_OK,
    summary="Actualizar etiquetas de intereses y preferencias temáticas (CU-03 / HU-03)",
    description="Permite actualizar directamente la lista de intereses temáticos, biografía y avatar del usuario.",
    response_description="Perfil actualizado con las nuevas preferencias",
)
def update_current_user_preferences(
    dto: PreferencesUpdateDTO,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfileDTO:
    """
    Actualiza específicamente las preferencias e intereses temáticos del usuario autenticado (CU-03).

    Args:
        dto (PreferencesUpdateDTO): Lista de etiquetas de interés y metadatos opcionales de perfil.
        current_user (User): Usuario autenticado en sesión.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        ProfileDTO: Perfil actualizado con las nuevas preferencias.
    """
    service = ProfileService(db)
    return service.update_preferences(current_user.id, dto)


@users_router.get(
    "/{user_id}",
    response_model=ProfileDTO,
    status_code=status.HTTP_200_OK,
    summary="Consultar información de un perfil por su ID (CU-03)",
    description="Obtiene el perfil público y preferencias de un usuario específico mediante su ID numérico.",
    response_description="Perfil del usuario solicitado",
)
def get_user_by_id(
    user_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfileDTO:
    """
    Consulta el perfil de un usuario específico por su identificador único (CU-03).

    Args:
        user_id (int): ID del usuario a consultar.
        current_user (User): Usuario autenticado que realiza la consulta.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        ProfileDTO: Datos del perfil solicitado.
    """
    service = ProfileService(db)
    return service.get_profile(user_id)
