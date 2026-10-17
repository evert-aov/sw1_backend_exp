from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# Configuración del motor SQLAlchemy para PostgreSQL
database_url = settings.database_url
if database_url.startswith("sqlite"):
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        echo=settings.DB_LOGGING,
    )
else:
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        echo=settings.DB_LOGGING,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base declarativa para todas las entidades
Base = declarative_base()


def load_all_entities():
    """Importa todas las entidades para que el metadata de SQLAlchemy las registre."""
    import app.auth.entity
    import app.experience.entity
    import app.booking.entity
    import app.matching.entity
    import app.live.entity


def reset_database() -> dict:
    """Vacía y limpia la base de datos completa eliminando y recreando todas las tablas en cascada."""
    load_all_entities()
    if settings.database_url.startswith("sqlite"):
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


def init_db():
    # Atajo optativo solo para desarrollo; en despliegues, Alembic administra el esquema.
    if settings.DB_SYNCHRONIZE:
        load_all_entities()
        Base.metadata.create_all(bind=engine)
        from app.core.seeder import seed_database
        seed_database()


def get_db():
    # Inyección de dependencia para sesiones de base de datos por petición
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Re-exportar para compatibilidad retroactiva con scripts y controladores del sistema
from app.core.seeder import seed_database, reset_and_seed_database
