import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Configuración general del proyecto
    PROJECT_NAME: str = "EXPERIENCIA API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"

    # Conexión a la base de datos principal (PostgreSQL)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/experiencia_db",
    )

    # Seguridad y autenticación JWT
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "super_secret_jwt_key_experiencia_2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas

    # Pasarela de pagos Stripe para reservas y suscripciones SaaS
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")

    # Orígenes permitidos para peticiones CORS (Angular Web y Flutter Móvil)
    CORS_ORIGINS: List[str] = [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:3000",
        "http://localhost:8080",
        "*",
    ]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
