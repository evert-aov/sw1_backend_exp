from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
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


# Endpoints de Autenticación (CU-01)
@auth_router.post("/register", response_model=ProfileDTO, status_code=status.HTTP_201_CREATED)
def register(dto: RegisterDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para registro de cuenta
    pass


@auth_router.post("/login", response_model=TokenResponseDTO)
def login(dto: LoginDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para autenticación con credenciales y entrega de JWT
    pass


# Endpoints de Perfil y Usuarios (CU-02)
@users_router.get("/me", response_model=ProfileDTO)
def get_current_user_profile(db: Session = Depends(get_db)):
    # Firma de endpoint para obtener perfil del usuario autenticado
    pass


@users_router.put("/me", response_model=ProfileDTO)
def update_current_user_profile(dto: ProfileUpdateDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para actualizar perfil y preferencias
    pass


@users_router.get("/{user_id}", response_model=ProfileDTO)
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    # Firma de endpoint para consultar usuario por ID
    pass
