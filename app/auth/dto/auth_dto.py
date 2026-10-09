from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr


# DTO para solicitud de inicio de sesión (CU-01)
class LoginDTO(BaseModel):
    email: EmailStr
    password: str


# DTO para registro de nuevo usuario (CU-01)
class RegisterDTO(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    email: EmailStr
    password: str
    phone: Optional[str] = None
    role: Optional[str] = "ATTENDEE"  # ATTENDEE, HOST, VENUE


# DTO con respuesta de token JWT generado tras login exitoso
class TokenResponseDTO(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str
    roles: List[str]


# DTO para actualización de perfil de usuario (CU-02)
class ProfileUpdateDTO(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    interests: Optional[List[str]] = None


# DTO de respuesta para consulta de perfil (CU-02)
class ProfileDTO(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    interests: List[str] = []
    roles: List[str] = []
    created_at: datetime

    class Config:
        from_attributes = True
