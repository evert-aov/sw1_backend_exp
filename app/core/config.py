from __future__ import annotations

import re
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    Configuración global transversal de la aplicación EXPERIENCIA API.
    Carga variables de entorno desde archivo `.env` o variables del sistema operativo,
    utilizando tipado moderno de Python 3.14.6 y Pydantic v2.
    """

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", case_sensitive=True, extra="ignore"
    )

    # Configuración general del proyecto
    PROJECT_NAME: str = "EXPERIENCIA API"
    VERSION: str = "1.0.0"
    PYTHON_TARGET_VERSION: str = "3.14.6"
    API_V1_STR: str = "/api"
    ENABLE_MAINTENANCE_ENDPOINTS: bool = False
    BOOKING_HOLD_MINUTES: int = Field(default=15, ge=1, le=120)
    PAYMENT_CURRENCY: str = Field(default="BOB", pattern="^[A-Z]{3}$")

    # Base de Datos PostgreSQL
    DB_HOST: str = "localhost"
    DB_PORT: int = Field(default=5432, ge=1, le=65535)
    DB_USER: str = ""
    DB_PASS: str = ""
    DB_NAME: str = "experiencia_db"
    # Desarrollo: aplica Alembic al arrancar. False: exige migración explícita previa.
    DB_SYNCHRONIZE: bool = False
    DB_LOGGING: bool = False

    # Seguridad JWT
    JWT_SECRET: str
    JWT_EXPIRES_IN: str = "1d"
    ALGORITHM: str = "HS256"

    # Pasarela de pagos Stripe
    # Hosted Checkout no necesita exponer esta clave al cliente; se conserva para futuras integraciones.
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    FRONTEND_URL: str = "http://localhost:3000"

    # Comisión de la plataforma por defecto (%)
    PLATFORM_FEE_PERCENTAGE: float = Field(default=10.0, ge=0.0, le=100.0)

    # Modelos OpenCV de estimación etaria (HU-16): rutas absolutas o relativas a la carpeta del backend.
    # Vacías o inexistentes: el estimador no se registra y la API informa estimator_configured=false.
    AGE_FACE_DETECTOR_PATH: str = ""
    AGE_CLASSIFIER_PROTOTXT_PATH: str = ""
    AGE_CLASSIFIER_MODEL_PATH: str = ""

    # URL PostgreSQL opcional; tiene prioridad sobre los campos DB_*.
    DATABASE_URL: str | None = None

    # Orígenes CORS permitidos
    CORS_ORIGINS: list[str] = [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:3000",
        "http://localhost:8080",
        "*",
    ]

    @field_validator("JWT_SECRET")
    @classmethod
    def jwt_secret_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("JWT_SECRET must not be empty.")
        return value

    @field_validator("JWT_EXPIRES_IN")
    @classmethod
    def validate_jwt_expiration(cls, value: str) -> str:
        if not re.fullmatch(r"[1-9][0-9]*([dhm])?", value.strip().lower()):
            raise ValueError(
                "JWT_EXPIRES_IN must be a positive integer with an optional d, h, or m suffix."
            )
        return value

    @property
    def database_url(self) -> str:
        """
        Construye la conexión PostgreSQL y conserva contraseñas con caracteres especiales.

        Returns:
            str: URI PostgreSQL para SQLAlchemy con el controlador psycopg2.
        """
        if self.DATABASE_URL:
            value = self.DATABASE_URL.strip()
            if value.startswith("postgres://"):
                value = "postgresql://" + value.removeprefix("postgres://")
            url = make_url(value)
            if url.get_backend_name() != "postgresql":
                raise ValueError("DATABASE_URL debe apuntar a PostgreSQL.")
            url = url.set(drivername="postgresql+psycopg2")
        else:
            if not self.DB_USER or not self.DB_NAME:
                raise ValueError(
                    "Configura DATABASE_URL o DB_USER y DB_NAME en experiencia_back/.env."
                )
            url = URL.create(
                "postgresql+psycopg2",
                username=self.DB_USER,
                password=self.DB_PASS,
                host=self.DB_HOST,
                port=self.DB_PORT,
                database=self.DB_NAME,
            )
        return url.render_as_string(hide_password=False)

    @property
    def access_token_expire_minutes(self) -> int:
        """
        Calcula el tiempo de expiración del token JWT en minutos a partir de `JWT_EXPIRES_IN`.

        Soporta sufijos de días (`d`), horas (`h`), minutos (`m`) o valores enteros directos.

        Returns:
            int: Duración de validez del token JWT en minutos.
        """
        val = self.JWT_EXPIRES_IN.strip().lower()
        if val.endswith("d"):
            return int(val[:-1]) * 24 * 60
        elif val.endswith("h"):
            return int(val[:-1]) * 60
        elif val.endswith("m"):
            return int(val[:-1])
        try:
            return int(val)
        except ValueError:
            return 60 * 24


# pydantic-settings resolves this required value from the environment at runtime.
settings = Settings()  # pyright: ignore[reportCallIssue]
