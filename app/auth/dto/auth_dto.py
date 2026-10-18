from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginDTO(BaseModel):
    """
    Contrato de datos de entrada para inicio de sesión con credenciales (CU-02 / HU-02).
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "email": "host@experiencia.com",
                "password": "Password123!",
            }
        },
    )

    email: EmailStr = Field(..., description="Correo electrónico registrado del usuario")
    password: str = Field(..., min_length=1, description="Contraseña de la cuenta en texto plano")


class RegisterDTO(BaseModel):
    """
    Contrato de datos de entrada para el registro de una nueva cuenta de usuario (CU-01 / HU-01).
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "first_name": "Valeria",
                "last_name": "Pareja Pérez",
                "email": "valeria@experiencia.com",
                "password": "Password123!",
                "phone": "+59170000099",
                "role": "ATTENDEE",
                "bio": "Apasionada por experiencias culturales y talleres creativos.",
                "interests": ["Arte", "Gastronomía", "Música en vivo"],
            }
        },
    )

    first_name: str = Field(..., min_length=2, max_length=100, description="Nombres del usuario")
    last_name: str | None = Field(default=None, max_length=100, description="Apellidos del usuario")
    email: EmailStr = Field(..., description="Correo electrónico único para la cuenta")
    password: str = Field(
        ...,
        min_length=6,
        max_length=72,
        description="Contraseña segura (mínimo 6 caracteres)",
    )
    phone: str | None = Field(default=None, max_length=20, description="Número de teléfono móvil")
    role: str | None = Field(
        default="ATTENDEE",
        description="Rol inicial asignado: ATTENDEE, HOST, VENUE o ADMIN",
    )
    avatar_url: str | None = Field(
        default=None,
        max_length=255,
        description="URL opcional de la fotografía o avatar de perfil",
    )
    bio: str | None = Field(default=None, max_length=1000, description="Biografía breve del usuario")
    interests: list[str] | None = Field(
        default=None,
        description="Etiquetas iniciales de intereses temáticos para el motor de matching",
    )

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        """Valida que el nombre no esté vacío ni compuesto solo por espacios."""
        clean = v.strip()
        if len(clean) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres válidos.")
        return clean


class TokenResponseDTO(BaseModel):
    """
    Contrato de respuesta tras autenticación o renovación exitosa de token JWT (CU-02 / HU-02).
    """

    model_config = ConfigDict(from_attributes=True)

    access_token: str = Field(..., description="Token JWT firmado digitalmente (HS256)")
    token_type: str = Field(default="bearer", description="Esquema de autenticación HTTP")
    user_id: str = Field(..., description="Identificador único del usuario autenticado (UUID)")
    email: EmailStr = Field(..., description="Correo electrónico del usuario autenticado")
    roles: list[str] = Field(
        default_factory=list,
        description="Lista de roles activos asignados al usuario",
    )


class LogoutResponseDTO(BaseModel):
    """
    Contrato de respuesta tras el cierre de sesión e invalidación del token JWT (CU-02 / HU-02).
    """

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(default="success", description="Estado de la operación de cierre de sesión")
    message: str = Field(
        default="Sesión cerrada correctamente. El token JWT ha sido revocado.",
        description="Mensaje descriptivo de confirmación de logout",
    )
    user_id: str = Field(..., description="ID del usuario que cerró sesión (UUID)")
    email: EmailStr = Field(..., description="Correo del usuario que cerró sesión")
    logged_out_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Fecha y hora UTC en que se revocó el token",
    )


class ProfileUpdateDTO(BaseModel):
    """
    Contrato de datos para actualización integral o parcial del perfil y preferencias (CU-03 / HU-03).
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "first_name": "Anfitrión",
                "last_name": "Actualizado",
                "phone": "+59170011223",
                "avatar_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=300",
                "bio": "Organizador de eventos gastronómicos y catas de café de especialidad.",
                "interests": ["Gastronomía", "Café de especialidad", "Networking", "Música en vivo"],
            }
        },
    )

    first_name: str | None = Field(default=None, min_length=2, max_length=100, description="Nombres")
    last_name: str | None = Field(default=None, max_length=100, description="Apellidos")
    phone: str | None = Field(default=None, max_length=20, description="Teléfono de contacto")
    avatar_url: str | None = Field(default=None, max_length=255, description="URL de foto de perfil")
    bio: str | None = Field(default=None, max_length=1000, description="Biografía personal o profesional")
    interests: list[str] | None = Field(
        default=None,
        description="Lista de etiquetas de intereses y preferencias temáticas",
    )


class PreferencesUpdateDTO(BaseModel):
    """
    Contrato especializado para actualizar preferencias, intereses temáticos, biografía y avatar (CU-03 / HU-03).
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    interests: list[str] = Field(
        ...,
        description="Lista actualizada de etiquetas de intereses para recomendaciones y matching",
    )
    bio: str | None = Field(default=None, max_length=1000, description="Biografía opcional actualizada")
    avatar_url: str | None = Field(default=None, max_length=255, description="URL de avatar opcional")


class ProfileDTO(BaseModel):
    """
    Contrato de respuesta con la información pública y preferencias del perfil de usuario (CU-01, CU-03 / HU-01, HU-03).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Identificador único del usuario (UUID)")
    first_name: str = Field(..., description="Nombres del usuario")
    last_name: str | None = Field(default=None, description="Apellidos del usuario")
    email: EmailStr = Field(..., description="Correo electrónico de la cuenta")
    phone: str | None = Field(default=None, description="Teléfono de contacto")
    avatar_url: str | None = Field(default=None, description="URL de la foto de perfil")
    bio: str | None = Field(default=None, description="Biografía del usuario")
    interests: list[str] = Field(
        default_factory=list,
        description="Etiquetas de intereses y preferencias configuradas",
    )
    roles: list[str] = Field(
        default_factory=list,
        description="Roles asignados al usuario en la plataforma",
    )
    is_active: bool = Field(default=True, description="Indica si la cuenta se encuentra activa")
    created_at: datetime = Field(..., description="Fecha y hora de creación de la cuenta")
