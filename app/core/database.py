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


def seed_default_roles():
    """Inicializa los roles predeterminados del sistema si no existen."""
    load_all_entities()
    from app.auth.entity.role import Role
    db = SessionLocal()
    try:
        roles_default = [
            ("ADMIN", "Administrador general con control total de la plataforma"),
            ("HOST", "Anfitrión u organizador que publica y dirige eventos"),
            ("VENUE", "Propietario o administrador de un establecimiento comercial"),
            ("ATTENDEE", "Usuario asistente que reserva y participa en experiencias"),
        ]
        for name, desc in roles_default:
            exists = db.query(Role).filter(Role.name == name).first()
            if not exists:
                db.add(Role(name=name, description=desc))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[Seed Warning] No se pudieron inicializar roles: {e}")
    finally:
        db.close()


def seed_default_users() -> list:
    """
    Inicializa usuarios por defecto con Admin como primer usuario (ID 1).
    Contraseña estándar para todos: Password123!
    """
    load_all_entities()
    from app.auth.entity.user import User
    from app.auth.entity.role import Role
    from app.auth.entity.user_role import UserRole
    from app.core.security import get_password_hash

    db = SessionLocal()
    seeded = []
    try:
        default_password_hash = get_password_hash("Password123!")
        
        users_default = [
            {
                "email": "admin@experiencia.com",
                "first_name": "Admin",
                "last_name": "Sistema",
                "phone": "+59170000004",
                "role": "ADMIN",
                "interests": ["Administración", "Métricas", "Seguridad"],
                "bio": "Administrador general de la plataforma EXPERIENCIA",
            },
            {
                "email": "host@experiencia.com",
                "first_name": "Anfitrión",
                "last_name": "Demo",
                "phone": "+59170000002",
                "role": "HOST",
                "interests": ["Eventos", "Talleres", "DJ"],
                "bio": "Anfitrión y organizador de experiencias",
            },
            {
                "email": "venue@experiencia.com",
                "first_name": "Local",
                "last_name": "Demo",
                "phone": "+59170000003",
                "role": "VENUE",
                "interests": ["Gastronomía", "Salones", "Espacios"],
                "bio": "Propietario de establecimiento comercial",
            },
            {
                "email": "attendee@experiencia.com",
                "first_name": "Asistente",
                "last_name": "Demo",
                "phone": "+59170000001",
                "role": "ATTENDEE",
                "interests": ["Música", "Networking", "Arte"],
                "bio": "Usuario asistente de demostración",
            },
            {
                "email": "nicol.guairaje@experiencia.com",
                "first_name": "Nicol",
                "last_name": "Guairaje",
                "phone": "+59170000000",
                "role": "HOST",
                "interests": ["Inteligencia Artificial", "Música Electrónica", "Eventos Sociales"],
                "bio": "Ingeniera de Software y Desarrolladora Backend FastAPI",
            },
        ]

        for u_data in users_default:
            user = db.query(User).filter(User.email == u_data["email"]).first()
            if not user:
                user = User(
                    email=u_data["email"],
                    first_name=u_data["first_name"],
                    last_name=u_data["last_name"],
                    phone=u_data["phone"],
                    hashed_password=default_password_hash,
                    interests=u_data["interests"],
                    bio=u_data["bio"],
                    is_active=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)

            # Asignar rol correspondiente
            role = db.query(Role).filter(Role.name == u_data["role"]).first()
            if role:
                has_role = (
                    db.query(UserRole)
                    .filter(UserRole.user_id == user.id, UserRole.role_id == role.id)
                    .first()
                )
                if not has_role:
                    db.add(UserRole(user_id=user.id, role_id=role.id))
                    db.commit()

            seeded.append({
                "id": user.id,
                "email": user.email,
                "name": f"{user.first_name} {user.last_name or ''}".strip(),
                "role": u_data["role"]
            })
        return seeded
    except Exception as e:
        db.rollback()
        print(f"[Seed Warning] No se pudieron inicializar usuarios: {e}")
        return []
    finally:
        db.close()


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


def seed_database() -> dict:
    """Puebla roles y usuarios por defecto."""
    load_all_entities()
    seed_default_roles()
    users = seed_default_users()
    return {
        "status": "success",
        "message": "Datos semilla insertados correctamente.",
        "users": users,
    }


def reset_and_seed_database() -> dict:
    """Limpia la base de datos en cascada y genera de inmediato los datos semilla."""
    reset_database()
    return seed_database()


def init_db():
    # Sincronización automática de tablas según variable DB_SYNCHRONIZE
    if settings.DB_SYNCHRONIZE:
        load_all_entities()
        Base.metadata.create_all(bind=engine)
        seed_default_roles()
        seed_default_users()


def get_db():
    # Inyección de dependencia para sesiones de base de datos por petición
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
