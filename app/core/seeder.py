"""
Módulo de Seeding: poblamiento y datos iniciales de prueba para EXPERIENCIA.
"""

from app.core.database import SessionLocal, load_all_entities, reset_database
from app.core.security import get_password_hash


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
                "bio": "Propietario de espacios y locales comerciales",
            },
            {
                "email": "attendee@experiencia.com",
                "first_name": "Asistente",
                "last_name": "Demo",
                "phone": "+59170000001",
                "role": "ATTENDEE",
                "interests": ["Música en vivo", "Arte", "Networking"],
                "bio": "Entusiasta de nuevas experiencias y talleres",
            },
            {
                "email": "nicol.gherbas@gmail.com",
                "first_name": "Nicol Melany",
                "last_name": "Guairaje Herbas",
                "phone": "+59178550186",
                "role": "ADMIN",
                "interests": ["Backend", "FastAPI", "Seguridad"],
                "bio": "Desarrolladora Backend - EXPERIENCIA",
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
                "role": u_data["role"],
            })
        return seeded
    except Exception as e:
        db.rollback()
        print(f"[Seed Warning] No se pudieron inicializar usuarios: {e}")
        return []
    finally:
        db.close()


def seed_default_categories() -> list:
    """Inicializa categorías temáticas base para el catálogo de experiencias."""
    load_all_entities()
    from app.experience.entity.category import Category

    db = SessionLocal()
    default_categories = [
        {"name": "Gastronomía", "description": "Catas, maridajes, cocina de autor y experiencias culinarias.", "icon_name": "restaurant"},
        {"name": "Arte y Pintura", "description": "Talleres de pintura, escultura, galerías y exposiciones interactivas.", "icon_name": "palette"},
        {"name": "Música y Conciertos", "description": "Sesiones acústicas, DJ sets, música en vivo y festivales íntimos.", "icon_name": "music_note"},
        {"name": "Talleres y Educación", "description": "Masterclasses, workshops prácticos y aprendizaje interactivo.", "icon_name": "school"},
        {"name": "Networking y Negocios", "description": "Encuentros profesionales, pitch sessions y comunidades tecnológicas.", "icon_name": "groups"},
    ]
    seeded = []
    try:
        for cat_data in default_categories:
            cat = db.query(Category).filter(Category.name == cat_data["name"]).first()
            if not cat:
                cat = Category(
                    name=cat_data["name"],
                    description=cat_data["description"],
                    icon_name=cat_data["icon_name"],
                )
                db.add(cat)
                db.commit()
                db.refresh(cat)
            seeded.append({"id": cat.id, "name": cat.name})
        return seeded
    except Exception as e:
        db.rollback()
        print(f"[Seed Warning] No se pudieron inicializar categorías: {e}")
        return []
    finally:
        db.close()


def seed_default_venues() -> list:
    """Inicializa locales físicos de prueba asociados al usuario de rol VENUE."""
    load_all_entities()
    from app.auth.entity.user import User
    from app.experience.entity.venue import Venue

    db = SessionLocal()
    try:
        venue_user = db.query(User).filter(User.email == "venue@experiencia.com").first()
        owner_id = venue_user.id if venue_user else None

        default_venues = [
            {
                "name": "Espacio Cultural Equipetrol",
                "address": "Av. San Martín #450",
                "city": "Santa Cruz de la Sierra",
                "zone": "Equipetrol",
                "latitude": -17.7712,
                "longitude": -63.1954,
                "max_capacity": 60,
                "phone": "+59170000010",
            },
            {
                "name": "Terraza Manzana 40",
                "address": "4to Anillo y Av. Busch",
                "city": "Santa Cruz de la Sierra",
                "zone": "Manzana 40",
                "latitude": -17.7654,
                "longitude": -63.1899,
                "max_capacity": 100,
                "phone": "+59170000011",
            },
        ]
        seeded = []
        for v_data in default_venues:
            venue = db.query(Venue).filter(Venue.name == v_data["name"]).first()
            if not venue:
                venue = Venue(
                    owner_id=owner_id,
                    name=v_data["name"],
                    address=v_data["address"],
                    city=v_data["city"],
                    zone=v_data["zone"],
                    latitude=v_data["latitude"],
                    longitude=v_data["longitude"],
                    max_capacity=v_data["max_capacity"],
                    phone=v_data["phone"],
                )
                db.add(venue)
                db.commit()
                db.refresh(venue)
            seeded.append({"id": venue.id, "name": venue.name, "zone": venue.zone})
        return seeded
    except Exception as e:
        db.rollback()
        print(f"[Seed Warning] No se pudieron inicializar locales: {e}")
        return []
    finally:
        db.close()


def seed_database() -> dict:
    """Puebla roles, usuarios, categorías y locales en un esquema ya migrado."""
    load_all_entities()
    seed_default_roles()
    users = seed_default_users()
    categories = seed_default_categories()
    venues = seed_default_venues()
    return {
        "status": "success",
        "message": "Datos semilla insertados correctamente.",
        "users": users,
        "categories": categories,
        "venues": venues,
    }


def reset_and_seed_database() -> dict:
    """Limpia la base de datos en cascada y genera de inmediato los datos semilla."""
    reset_database()
    return seed_database()
