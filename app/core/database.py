from __future__ import annotations

from collections.abc import Generator
from typing import Any
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from app.core.config import settings


def _build_engine() -> tuple[Engine, str]:
    """
    Construye exclusivamente PostgreSQL sin abrir conexiones al importar.
    Los errores de conexión se propagan durante la comprobación de arranque.

    Returns:
        tuple[Engine, str]: Instancia del motor SQLAlchemy y la URL efectiva de conexión.
    """
    configured_url = settings.database_url
    pg_engine = create_engine(
        configured_url,
        pool_pre_ping=True,
        echo=settings.DB_LOGGING,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )
    return pg_engine, configured_url


engine, active_database_url = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base declarativa para todas las entidades ORM
Base = declarative_base()


def generate_uuid() -> str:
    """
    Genera un identificador único global UUIDv7 (basado en tiempo y ordenable cronológicamente),
    con fallback transparente a UUIDv4 si el runtime no soporta uuid7.

    Returns:
        str: Identificador UUID de 36 caracteres.
    """
    import uuid

    if hasattr(uuid, "uuid7"):
        return str(uuid.uuid7())
    return str(uuid.uuid4())


def load_all_entities() -> None:
    """
    Importa todos los paquetes de entidades del dominio para que el registro
    `Base.metadata` de SQLAlchemy reconozca las tablas relacionales vigentes.
    """
    import app.auth.entity  # noqa: F401
    import app.experience.entity  # noqa: F401
    import app.booking.entity  # noqa: F401
    import app.matching.entity  # noqa: F401
    import app.live.entity  # noqa: F401
    import app.notifications.entity  # noqa: F401


def reset_database() -> dict[str, Any]:
    """
    Vacía y limpia la base de datos completa eliminando y recreando todas las tablas en cascada.

    Returns:
        dict[str, Any]: Resumen del estado del reinicio y número de tablas recreadas.
    """
    load_all_entities()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    Base.metadata.create_all(bind=engine)

    return {
        "status": "success",
        "message": "Base de datos reiniciada y todas las tablas recreadas limpiamente en cascada.",
        "tables_recreated": len(Base.metadata.tables),
    }


def init_db() -> None:
    """
    Prepara PostgreSQL antes de aceptar tráfico. DB_SYNCHRONIZE habilita Alembic;
    desactivado, solo verifica estructura. Nunca reinicia ni siembra datos.
    """
    with engine.begin() as conn:
        conn.execute(text("SELECT 1"))
        if settings.DB_SYNCHRONIZE:
            from app.core.migrations import migrate_connection

            migrate_connection(conn)
        else:
            from app.core.schema import validate_database_schema

            validate_database_schema(conn)


def get_db() -> Generator[Session, None, None]:
    """
    Dependencia de FastAPI para proveer una sesión transaccional de base de datos por petición HTTP,
    garantizando el cierre seguro de la conexión al finalizar el ciclo de vida del request.

    Yields:
        Session: Sesión activa de SQLAlchemy.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_database() -> dict[str, Any]:
    """
    Delega la ejecución idempotente del seeder de datos iniciales del Sprint 1.

    Returns:
        dict[str, Any]: Resumen de datos semilla insertados.
    """
    from app.core.seeder import seed_database as _seed_database

    return _seed_database()


def reset_and_seed_database() -> dict[str, Any]:
    """
    Delega el reinicio en cascada y poblamiento inmediato de datos semilla del Sprint 1.

    Returns:
        dict[str, Any]: Resumen de datos semilla recreados.
    """
    from app.core.seeder import reset_and_seed_database as _reset_and_seed_database

    return _reset_and_seed_database()

