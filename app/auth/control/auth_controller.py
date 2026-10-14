from typing import List
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_active_user
from app.auth.entity.user import User
from app.auth.dto.auth_dto import (
    RegisterDTO,
    LoginDTO,
    TokenResponseDTO,
    ProfileDTO,
    ProfileUpdateDTO,
)
from app.auth.service.auth_service import AuthService
from app.auth.service.profile_service import ProfileService

auth_router = APIRouter(prefix="/auth", tags=["Auth Controller (CU-01)"])
users_router = APIRouter(prefix="/users", tags=["Users Controller (CU-02)"])


# ==========================================
# Endpoints de Autenticación (CU-01)
# ==========================================

@auth_router.post(
    "/register",
    response_model=ProfileDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una nueva cuenta de usuario (HU-01)",
    description="Permite a un visitante registrarse proporcionando datos personales, correo, contraseña y rol deseado.",
)
def register(dto: RegisterDTO, db: Session = Depends(get_db)):
    service = AuthService(db)
    return service.register(dto)


@auth_router.post(
    "/login",
    response_model=TokenResponseDTO,
    summary="Iniciar sesión y obtener token JWT (HU-02)",
    description="Valida las credenciales ingresadas y emite un JWT firmado para autenticar peticiones subsecuentes.",
)
def login(dto: LoginDTO, db: Session = Depends(get_db)):
    service = AuthService(db)
    return service.login(dto)


@auth_router.post(
    "/refresh",
    response_model=TokenResponseDTO,
    summary="Renovar token JWT de acceso (HU-02)",
    description="Renueva un token válido antes de su expiración para mantener la sesión activa.",
)
def refresh_token(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    return service.refresh_token_for_user(current_user)


# ==========================================
# Endpoints de Perfil y Usuarios (CU-02)
# ==========================================

@users_router.get(
    "",
    response_model=List[ProfileDTO],
    summary="Listar todos los usuarios registrados (HU-03 / Gestión de Usuarios)",
    description="Consulta la lista completa de usuarios del sistema con sus roles asociados (Requiere estar autenticado).",
)
def list_users(
    skip: int = Query(0, ge=0, description="Número de registros a omitir"),
    limit: int = Query(100, ge=1, le=500, description="Límite de usuarios por página"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)
    return service.list_users(skip=skip, limit=limit)


@users_router.get(
    "/me",
    response_model=ProfileDTO,
    summary="Consultar el perfil del usuario autenticado (HU-03)",
    description="Obtiene la información personal, foto de perfil, biografía y etiquetas de intereses del usuario actual.",
)
def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)
    return service.get_profile(current_user.id)


@users_router.put(
    "/me",
    response_model=ProfileDTO,
    summary="Actualizar perfil y preferencias del usuario autenticado (HU-03)",
    description="Permite modificar nombres, teléfono, foto, biografía y la lista de etiquetas de intereses para matching.",
)
def update_current_user_profile(
    dto: ProfileUpdateDTO,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)
    return service.update_profile(current_user.id, dto)


@users_router.get(
    "/{user_id}",
    response_model=ProfileDTO,
    summary="Consultar información de un perfil por su ID",
    description="Permite consultar el perfil público de otro usuario registrado (requiere autenticación).",
)
def get_user_by_id(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    service = ProfileService(db)
    return service.get_profile(user_id)
