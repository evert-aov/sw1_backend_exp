from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# Configuración del motor SQLAlchemy para PostgreSQL
database_url = settings.DATABASE_URL
if database_url.startswith("sqlite"):
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
else:
    engine = create_engine(database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base declarativa para todas las entidades
Base = declarative_base()


def get_db():
    # Inyección de dependencia para sesiones de base de datos por petición
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
