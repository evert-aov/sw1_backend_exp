from sqlalchemy import create_engine
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


def init_db():
    # Sincronización automática de tablas según variable DB_SYNCHRONIZE
    if settings.DB_SYNCHRONIZE:
        # Importar todas las entidades para que el metadata las registre antes de create_all
        import app.auth.entity
        import app.experience.entity
        import app.booking.entity
        import app.matching.entity
        import app.live.entity

        Base.metadata.create_all(bind=engine)


def get_db():
    # Inyección de dependencia para sesiones de base de datos por petición
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
