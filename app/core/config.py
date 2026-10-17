import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    # Configuración general del proyecto
    PROJECT_NAME: str = "EXPERIENCIA API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"

    # Base de Datos PostgreSQL
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", 5432))
    DB_USER: str = os.getenv("DB_USER", "evert")
    DB_PASS: str = os.getenv("DB_PASS", "nakroth")
    DB_NAME: str = os.getenv("DB_NAME", "experiencia_db")
    DB_SYNCHRONIZE: bool = os.getenv("DB_SYNCHRONIZE", "false").lower() in ("true", "1", "t")
    DB_LOGGING: bool = os.getenv("DB_LOGGING", "false").lower() in ("true", "1", "t")

    # Seguridad JWT
    JWT_SECRET: str = os.getenv(
        "JWT_SECRET",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiYWRtaW4iOnRydWUsImlhdCI6MTUxNjIzOTAyMn0.KMUFsIDTnFmyG3nMiGM6H9FNFUROf3wh7SmqJp-QV30",
    )
    JWT_EXPIRES_IN: str = os.getenv("JWT_EXPIRES_IN", "1d")
    ALGORITHM: str = "HS256"

    # Pasarela de pagos Stripe
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")

    # Comisión de la plataforma por defecto
    PLATFORM_FEE_PERCENTAGE: float = float(os.getenv("PLATFORM_FEE_PERCENTAGE", 10.0))

    # URL de conexión directa opcional (ideal para Neon Tech, AWS RDS, Render)
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")

    # Orígenes CORS permitidos
    CORS_ORIGINS: List[str] = [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:3000",
        "http://localhost:8080",
        "*",
    ]

    @property
    def database_url(self) -> str:
        # Si se especifica DATABASE_URL (ej. Neon Tech en la nube o AWS), normalizar el dialecto a psycopg2
        if self.DATABASE_URL:
            url = self.DATABASE_URL.strip()
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg2://", 1)
            elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
            return url
        # Si no, construir desde variables individuales de PostgreSQL local
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def access_token_expire_minutes(self) -> int:
        # Convierte cadenas como "1d", "2h", "60m" o números en minutos
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


settings = Settings()
