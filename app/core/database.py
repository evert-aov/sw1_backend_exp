from __future__ import annotations

import math
from collections.abc import Generator
from typing import Any
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from app.core.config import settings


def _register_sqlite_math_functions(target_engine: Engine) -> None:
    """
    Registra funciones trigonométricas y matemáticas estándar en conexiones SQLite
    para garantizar compatibilidad total con la fórmula de Haversine (CU-05 Geolocalización).

    Args:
        target_engine (Engine): Motor SQLAlchemy sobre el que se registran las funciones.
    """

    @event.listens_for(target_engine, "connect")
    def _on_connect(dbapi_connection: Any, _connection_record: Any) -> None:
        if hasattr(dbapi_connection, "create_function"):
            dbapi_connection.create_function(
                "radians", 1, lambda x: math.radians(float(x)) if x is not None else None
            )
            dbapi_connection.create_function(
                "sin", 1, lambda x: math.sin(float(x)) if x is not None else None
            )
            dbapi_connection.create_function(
                "cos", 1, lambda x: math.cos(float(x)) if x is not None else None
            )
            dbapi_connection.create_function(
                "asin",
                1,
                lambda x: math.asin(max(-1.0, min(1.0, float(x)))) if x is not None else None,
            )
            dbapi_connection.create_function(
                "sqrt",
                1,
                lambda x: math.sqrt(max(0.0, float(x))) if x is not None else None,
            )
            dbapi_connection.create_function(
                "pow",
                2,
                lambda x, y: math.pow(float(x), float(y))
                if x is not None and y is not None
                else None,
            )


def _build_engine() -> tuple[Engine, str]:
    """
    Construye el motor SQLAlchemy principal. Si PostgreSQL local no está disponible
    en el entorno de ejecución actual, aplica un fallback transparente a SQLite local
    con soporte completo de funciones geoespaciales Haversine.

    Returns:
        tuple[Engine, str]: Instancia del motor SQLAlchemy y la URL efectiva de conexión.
    """
    import socket

    configured_url = settings.database_url
    if configured_url.startswith("sqlite"):
        sqlite_engine = create_engine(
            configured_url,
            connect_args={"check_same_thread": False},
            echo=settings.DB_LOGGING,
        )
        _register_sqlite_math_functions(sqlite_engine)
        return sqlite_engine, configured_url

    pg_reachable = False
    try:
        with socket.create_connection((settings.DB_HOST, settings.DB_PORT), timeout=0.1):
            pg_reachable = True
    except OSError:
        pg_reachable = False

    if pg_reachable:
        pg_engine = create_engine(
            configured_url,
            pool_pre_ping=True,
            echo=settings.DB_LOGGING,
            connect_args={"connect_timeout": 1},
        )
        try:
            with pg_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return pg_engine, configured_url
        except Exception:
            pass

    fallback_url = "sqlite:///./experiencia_dev.db"
    sqlite_engine = create_engine(
        fallback_url,
        connect_args={"check_same_thread": False},
        echo=settings.DB_LOGGING,
    )
    _register_sqlite_math_functions(sqlite_engine)
    return sqlite_engine, fallback_url


engine, active_database_url = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base declarativa para todas las entidades ORM
Base = declarative_base()


def load_all_entities() -> None:
    """
    Importa todos los paquetes de entidades del dominio para que el registro
    `Base.metadata` de SQLAlchemy reconozca las 19 tablas relacionales.
    """
    import app.auth.entity  # noqa: F401
    import app.experience.entity  # noqa: F401
    import app.booking.entity  # noqa: F401
    import app.matching.entity  # noqa: F401
    import app.live.entity  # noqa: F401


def reset_database() -> dict[str, Any]:
    """
    Vacía y limpia la base de datos completa eliminando y recreando todas las tablas en cascada.

    Returns:
        dict[str, Any]: Resumen del estado del reinicio y número de tablas recreadas.
    """
    load_all_entities()
    is_sqlite = str(engine.url).startswith("sqlite")
    if is_sqlite:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    else:
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
            conn.commit()
        Base.metadata.create_all(bind=engine)

    return {
        "status": "success",
        "message": "Base de datos reiniciada y todas las tablas recreadas limpiamente en cascada.",
        "tables_recreated": len(Base.metadata.tables),
    }


def init_db() -> None:
    """
    Inicializa el esquema relacional y ejecuta el seeder de datos de prueba
    cuando `DB_SYNCHRONIZE` está habilitado o se utiliza la base de datos local de desarrollo.
    """
    if settings.DB_SYNCHRONIZE or str(engine.url).startswith("sqlite"):
        load_all_entities()
        Base.metadata.create_all(bind=engine)
        from app.core.seeder import seed_database

        seed_database()


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

