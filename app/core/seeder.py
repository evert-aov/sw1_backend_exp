"""
Módulo de Seeding: poblamiento idempotente de datos iniciales de prueba para EXPERIENCIA (Sprint 1).
Cubre roles, usuarios del equipo/demostración, categorías temáticas, establecimientos geolocalizados
y experiencias publicadas (presenciales, virtuales e híbridas).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from app.core.database import SessionLocal, load_all_entities, reset_database
from app.core.security import get_password_hash


def seed_default_roles() -> list[str]:
    """
    Inicializa los 4 roles predeterminados del sistema (`ADMIN`, `HOST`, `VENUE`, `ATTENDEE`) si no existen.

    Returns:
        list[str]: Lista de nombres de roles presentes en la base de datos.
    """
    load_all_entities()
    from app.auth.entity.role import Role

    db = SessionLocal()
    seeded_roles: list[str] = []
    try:
        roles_default: list[tuple[str, str]] = [
            ("ADMIN", "Administrador general con control total de la plataforma"),
            ("HOST", "Anfitrión u organizador que publica y dirige eventos"),
            ("VENUE", "Propietario o administrador de un establecimiento comercial"),
            ("ATTENDEE", "Usuario asistente que reserva y participa en experiencias"),
        ]
        for name, desc in roles_default:
            exists = db.query(Role).filter(Role.name == name).first()
            if not exists:
                db.add(Role(name=name, description=desc))
            seeded_roles.append(name)
        db.commit()
        return seeded_roles
    except Exception as e:
        db.rollback()
        print(f"[Seed Warning] No se pudieron inicializar roles: {e}")
        return []
    finally:
        db.close()


def seed_default_users() -> list[dict[str, Any]]:
    """
    Inicializa los usuarios por defecto de demostración y del equipo de desarrollo del Sprint 1.
    Contraseña estándar para todas las cuentas semilla: `Password123!`

    Returns:
        list[dict[str, Any]]: Resumen de usuarios semilla creados o verificados.
    """
    load_all_entities()
    from app.auth.entity.role import Role
    from app.auth.entity.user import User
    from app.auth.entity.user_role import UserRole

    db = SessionLocal()
    seeded: list[dict[str, Any]] = []
    try:
        default_password_hash = get_password_hash("Password123!")

        users_default: list[dict[str, Any]] = [
            {
                "email": "admin@experiencia.com",
                "first_name": "Admin",
                "last_name": "Sistema",
                "phone": "+59170000004",
                "role": "ADMIN",
                "avatar_url": "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=300",
                "interests": ["Administración", "Métricas", "Seguridad"],
                "bio": "Administrador general de la plataforma EXPERIENCIA",
            },
            {
                "email": "host@experiencia.com",
                "first_name": "Anfitrión",
                "last_name": "Demo",
                "phone": "+59170000002",
                "role": "HOST",
                "avatar_url": "https://images.unsplash.com/photo-1570295999919-56ceb5ecca61?w=300",
                "interests": ["Eventos", "Talleres", "DJ", "Gastronomía"],
                "bio": "Anfitrión y organizador certificado de experiencias culturales y gastronómicas",
            },
            {
                "email": "venue@experiencia.com",
                "first_name": "Local",
                "last_name": "Demo",
                "phone": "+59170000003",
                "role": "VENUE",
                "avatar_url": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=300",
                "interests": ["Gastronomía", "Salones", "Espacios", "Conciertos"],
                "bio": "Propietario de espacios culturales y terrazas para eventos en Santa Cruz",
            },
            {
                "email": "attendee@experiencia.com",
                "first_name": "Asistente",
                "last_name": "Demo",
                "phone": "+59170000001",
                "role": "ATTENDEE",
                "avatar_url": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=300",
                "interests": ["Música en vivo", "Arte", "Networking", "Café de especialidad"],
                "bio": "Entusiasta de nuevas experiencias, catas y talleres creativos",
            },
            {
                "email": "nicol.gherbas@gmail.com",
                "first_name": "Nicol Melany",
                "last_name": "Guairaje Herbas",
                "phone": "+59178550186",
                "role": "ADMIN",
                "avatar_url": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=300",
                "interests": ["Backend", "FastAPI", "Seguridad", "JWT"],
                "bio": "Desarrolladora Backend FastAPI - EXPERIENCIA",
            },
            {
                "email": "evert.rodriguez@experiencia.com",
                "first_name": "Evert",
                "last_name": "Rodríguez Arauz",
                "phone": "+59170000005",
                "role": "HOST",
                "avatar_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300",
                "interests": ["Product Owner", "Visión Artificial", "Smart Host", "Tecnología"],
                "bio": "Product Owner Sprint 1 & Anfitrión de experiencias tecnológicas",
            },
            {
                "email": "valeria.pareja@experiencia.com",
                "first_name": "Valeria",
                "last_name": "Pareja Pérez",
                "phone": "+59170000006",
                "role": "ATTENDEE",
                "avatar_url": "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=300",
                "interests": ["Arte y Pintura", "Diseño UI/UX", "Gastronomía"],
                "bio": "Desarrolladora Frontend Angular & Exploradora de experiencias artísticas",
            },
            {
                "email": "ricardo.rivero@experiencia.com",
                "first_name": "Ricardo Brian",
                "last_name": "Rivero Flores",
                "phone": "+59170000007",
                "role": "HOST",
                "avatar_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=300",
                "interests": ["Música y Conciertos", "Flutter", "Eventos Móviles"],
                "bio": "Anfitrión de sesiones acústicas y desarrollador móvil",
            },
            {
                "email": "douglas.rojas@experiencia.com",
                "first_name": "Douglas Ismael",
                "last_name": "Rojas Rivero",
                "phone": "+59170000008",
                "role": "VENUE",
                "avatar_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300",
                "interests": ["Geolocalización", "Machine Learning", "Espacios Culturales"],
                "bio": "Administrador de espacios inteligentes y modelado geoespacial",
            },
            {
                "email": "gabriela.crespo@experiencia.com",
                "first_name": "Gabriela Belén",
                "last_name": "Crespo Cárdenas",
                "phone": "+59170000009",
                "role": "ATTENDEE",
                "avatar_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=300",
                "interests": ["Talleres y Educación", "Bienestar", "Networking"],
                "bio": "Scrum Master Sprint 1 & Participante activa de workshops",
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
                    avatar_url=u_data.get("avatar_url"),
                    hashed_password=default_password_hash,
                    interests=u_data["interests"],
                    bio=u_data["bio"],
                    is_active=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)

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

            seeded.append(
                {
                    "id": user.id,
                    "email": user.email,
                    "name": f"{user.first_name} {user.last_name or ''}".strip(),
                    "role": u_data["role"],
                }
            )
        return seeded
    except Exception as e:
        db.rollback()
        print(f"[Seed Warning] No se pudieron inicializar usuarios: {e}")
        return []
    finally:
        db.close()


def seed_default_categories() -> list[dict[str, Any]]:
    """
    Inicializa las categorías temáticas base para el catálogo de experiencias (CU-04, CU-05).

    Returns:
        list[dict[str, Any]]: Lista de categorías semilla con su `id` y `name`.
    """
    load_all_entities()
    from app.experience.entity.category import Category

    db = SessionLocal()
    default_categories: list[dict[str, str]] = [
        {
            "name": "Gastronomía",
            "description": "Catas, maridajes, cocina de autor y experiencias culinarias.",
            "icon_name": "restaurant",
        },
        {
            "name": "Arte y Pintura",
            "description": "Talleres de pintura, escultura, galerías y exposiciones interactivas.",
            "icon_name": "palette",
        },
        {
            "name": "Música y Conciertos",
            "description": "Sesiones acústicas, DJ sets, música en vivo y festivales íntimos.",
            "icon_name": "music_note",
        },
        {
            "name": "Talleres y Educación",
            "description": "Masterclasses, workshops prácticos y aprendizaje interactivo.",
            "icon_name": "school",
        },
        {
            "name": "Networking y Negocios",
            "description": "Encuentros profesionales, pitch sessions y comunidades tecnológicas.",
            "icon_name": "groups",
        },
        {
            "name": "Bienestar y Outdoors",
            "description": "Sesiones de mindfulness, yoga al aire libre, senderismo y desconexión.",
            "icon_name": "self_improvement",
        },
    ]
    seeded: list[dict[str, Any]] = []
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


def seed_default_venues() -> list[dict[str, Any]]:
    """
    Inicializa establecimientos físicos geolocalizados en distintas zonas urbanas de Santa Cruz de la Sierra
    para pruebas de publicación (CU-04) y búsqueda por radio geográfico Haversine (CU-05).

    Returns:
        list[dict[str, Any]]: Lista de locales semilla creados.
    """
    load_all_entities()
    from app.auth.entity.user import User
    from app.experience.entity.venue import Venue

    db = SessionLocal()
    try:
        venue_user = db.query(User).filter(User.email == "venue@experiencia.com").first()
        owner_id = venue_user.id if venue_user else None

        default_venues: list[dict[str, Any]] = [
            {
                "name": "Espacio Cultural Equipetrol",
                "address": "Av. San Martín #450, Calle 7 Este",
                "city": "Santa Cruz de la Sierra",
                "zone": "Equipetrol",
                "latitude": -17.7712,
                "longitude": -63.1954,
                "max_capacity": 60,
                "phone": "+59170000010",
            },
            {
                "name": "Terraza Manzana 40",
                "address": "Av. San Martín y 4to Anillo, Torre 2 Piso 12",
                "city": "Santa Cruz de la Sierra",
                "zone": "Manzana 40",
                "latitude": -17.7654,
                "longitude": -63.1899,
                "max_capacity": 100,
                "phone": "+59170000011",
            },
            {
                "name": "Patio Histórico Casco Viejo",
                "address": "Calle Sucre #145, a una cuadra de la Plaza 24 de Septiembre",
                "city": "Santa Cruz de la Sierra",
                "zone": "Centro",
                "latitude": -17.7833,
                "longitude": -63.1821,
                "max_capacity": 80,
                "phone": "+59170000012",
            },
            {
                "name": "Jardín Botánico Lounge Urubó",
                "address": "Km 3 Camino a Porongo, Colinas del Urubó",
                "city": "Santa Cruz de la Sierra",
                "zone": "Urubó",
                "latitude": -17.7520,
                "longitude": -63.2245,
                "max_capacity": 120,
                "phone": "+59170000013",
            },
            {
                "name": "Galería Las Palmas Studio",
                "address": "Av. Ibérica #88, Barrio Las Palmas",
                "city": "Santa Cruz de la Sierra",
                "zone": "Las Palmas",
                "latitude": -17.7895,
                "longitude": -63.2040,
                "max_capacity": 45,
                "phone": "+59170000014",
            },
        ]
        seeded: list[dict[str, Any]] = []
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
            seeded.append(
                {
                    "id": venue.id,
                    "name": venue.name,
                    "zone": venue.zone,
                    "latitude": venue.latitude,
                    "longitude": venue.longitude,
                }
            )
        return seeded
    except Exception as e:
        db.rollback()
        print(f"[Seed Warning] No se pudieron inicializar locales: {e}")
        return []
    finally:
        db.close()


def seed_default_experiences() -> list[dict[str, Any]]:
    """
    Inicializa experiencias diversas (presenciales, virtuales e híbridas) con fechas futuras
    para probar inmediatamente la gestión de eventos (CU-04) y la exploración del catálogo
    por geolocalización, zona, categoría, modalidad y precio (CU-05).

    Returns:
        list[dict[str, Any]]: Lista de experiencias semilla publicadas.
    """
    load_all_entities()
    from app.auth.entity.user import User
    from app.experience.entity.category import Category
    from app.experience.entity.experience import (
        Experience,
        ExperienceStatusEnum,
        ModalityEnum,
    )
    from app.experience.entity.venue import Venue

    db = SessionLocal()
    seeded: list[dict[str, Any]] = []
    try:
        host_user = db.query(User).filter(User.email == "host@experiencia.com").first()
        second_host = (
            db.query(User).filter(User.email == "evert.rodriguez@experiencia.com").first()
            or host_user
        )
        if not host_user:
            return []

        categories_map = {c.name: c.id for c in db.query(Category).all()}
        venues_map = {v.name: v.id for v in db.query(Venue).all()}

        base_future = (
            datetime.now(timezone.utc)
            .replace(hour=19, minute=0, second=0, microsecond=0, tzinfo=None)
            + timedelta(days=7)
        )

        default_experiences: list[dict[str, Any]] = [
            {
                "host_id": host_user.id,
                "category_name": "Gastronomía",
                "venue_name": "Espacio Cultural Equipetrol",
                "title": "Cata Sensorial de Café de Especialidad de los Yungas",
                "description": (
                    "Experiencia inmersiva guiada por baristas campeones nacionales probando 4 variedades "
                    "de granos de altura mediante V60, Chemex y Aeropress con maridaje artesanal."
                ),
                "cover_image_url": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=800",
                "modality": ModalityEnum.IN_PERSON,
                "status": ExperienceStatusEnum.OPEN,
                "price": 120.0,
                "min_capacity": 6,
                "max_capacity": 20,
                "reserved_slots": 4,
                "event_date": base_future,
                "duration_minutes": 120,
                "virtual_meeting_url": None,
            },
            {
                "host_id": host_user.id,
                "category_name": "Arte y Pintura",
                "venue_name": "Galería Las Palmas Studio",
                "title": "Noche de Pintura Acrílica Neón, Vino y Jazz Acústico",
                "description": (
                    "Taller creativo de pintura bajo luz ultravioleta acompañado de degustación de vinos "
                    "tintos de Tarija y música jazz en vivo. Incluye lienzo y todos los materiales."
                ),
                "cover_image_url": "https://images.unsplash.com/photo-1460661419201-fd4cecdf8a8b?w=800",
                "modality": ModalityEnum.IN_PERSON,
                "status": ExperienceStatusEnum.CONFIRMED,
                "price": 150.0,
                "min_capacity": 8,
                "max_capacity": 25,
                "reserved_slots": 10,
                "event_date": base_future + timedelta(days=2),
                "duration_minutes": 150,
                "virtual_meeting_url": None,
            },
            {
                "host_id": second_host.id if second_host else host_user.id,
                "category_name": "Música y Conciertos",
                "venue_name": "Terraza Manzana 40",
                "title": "Sunset Rooftop Electronic & Live Vinyl Session",
                "description": (
                    "Sesión exclusiva en terraza con vista panorámica de la ciudad, vinilos en vivo, "
                    "house melódico y monitoreo interactivo Smart Host."
                ),
                "cover_image_url": "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=800",
                "modality": ModalityEnum.IN_PERSON,
                "status": ExperienceStatusEnum.CONFIRMED,
                "price": 95.0,
                "min_capacity": 15,
                "max_capacity": 80,
                "reserved_slots": 22,
                "event_date": base_future + timedelta(days=4, hours=1),
                "duration_minutes": 180,
                "virtual_meeting_url": None,
            },
            {
                "host_id": second_host.id if second_host else host_user.id,
                "category_name": "Talleres y Educación",
                "venue_name": None,
                "title": "Masterclass en Vivo: Arquitecturas Limpias con Python 3.14 y FastAPI",
                "description": (
                    "Workshop técnico interactivo sobre diseño de APIs RESTful de alto rendimiento, "
                    "tipado moderno Python 3.14.6, Pydantic v2 y pruebas automatizadas."
                ),
                "cover_image_url": "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=800",
                "modality": ModalityEnum.VIRTUAL,
                "status": ExperienceStatusEnum.CONFIRMED,
                "price": 0.0,
                "min_capacity": 10,
                "max_capacity": 100,
                "reserved_slots": 14,
                "event_date": base_future + timedelta(days=5, hours=-1),
                "duration_minutes": 120,
                "virtual_meeting_url": "https://meet.experiencia.com/fastapi-python314",
            },
            {
                "host_id": second_host.id if second_host else host_user.id,
                "category_name": "Networking y Negocios",
                "venue_name": "Terraza Manzana 40",
                "title": "Founder & Tech Mixer: IA y Visión Artificial en Tiempo Real",
                "description": (
                    "Encuentro híbrido de fundadores, desarrolladores e inversionistas para explorar "
                    "aplicaciones reales de visión por computadora respetando privacidad GDPR."
                ),
                "cover_image_url": "https://images.unsplash.com/photo-1515187029135-18ee286d815b?w=800",
                "modality": ModalityEnum.HYBRID,
                "status": ExperienceStatusEnum.OPEN,
                "price": 75.0,
                "min_capacity": 10,
                "max_capacity": 50,
                "reserved_slots": 6,
                "event_date": base_future + timedelta(days=8),
                "duration_minutes": 120,
                "virtual_meeting_url": "https://meet.experiencia.com/tech-mixer-scz",
            },
            {
                "host_id": host_user.id,
                "category_name": "Gastronomía",
                "venue_name": "Patio Histórico Casco Viejo",
                "title": "Taller de Cocina de Autor Amazónica y Fusión Cruceña",
                "description": (
                    "Aprende técnicas culinarias contemporáneas utilizando ingredientes nativos amazónicos "
                    "y chiquitanos en una casona patrimonial del centro histórico."
                ),
                "cover_image_url": "https://images.unsplash.com/photo-1556910103-1c02745aae4d?w=800",
                "modality": ModalityEnum.IN_PERSON,
                "status": ExperienceStatusEnum.OPEN,
                "price": 180.0,
                "min_capacity": 5,
                "max_capacity": 18,
                "reserved_slots": 3,
                "event_date": base_future + timedelta(days=10),
                "duration_minutes": 150,
                "virtual_meeting_url": None,
            },
            {
                "host_id": host_user.id,
                "category_name": "Bienestar y Outdoors",
                "venue_name": "Jardín Botánico Lounge Urubó",
                "title": "Sesión de Mindfulness, Sound Healing y Yoga al Atardecer",
                "description": (
                    "Conexión con la naturaleza en las colinas del Urubó mediante cuencos tibetanos, "
                    "respiración consciente y práctica guiada de vinyasa yoga."
                ),
                "cover_image_url": "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800",
                "modality": ModalityEnum.IN_PERSON,
                "status": ExperienceStatusEnum.OPEN,
                "price": 65.0,
                "min_capacity": 8,
                "max_capacity": 35,
                "reserved_slots": 5,
                "event_date": base_future + timedelta(days=12, hours=-2),
                "duration_minutes": 90,
                "virtual_meeting_url": None,
            },
            {
                "host_id": host_user.id,
                "category_name": "Música y Conciertos",
                "venue_name": "Patio Histórico Casco Viejo",
                "title": "Concierto Íntimo de Cuerdas y Flamenco Contemporáneo",
                "description": (
                    "Velada acústica a la luz de las velas con cuarteto de cuerdas y guitarra flamenca "
                    "en el corazón del Casco Viejo."
                ),
                "cover_image_url": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=800",
                "modality": ModalityEnum.IN_PERSON,
                "status": ExperienceStatusEnum.OPEN,
                "price": 110.0,
                "min_capacity": 12,
                "max_capacity": 60,
                "reserved_slots": 7,
                "event_date": base_future + timedelta(days=14, hours=1),
                "duration_minutes": 120,
                "virtual_meeting_url": None,
            },
        ]

        for exp_data in default_experiences:
            existing = (
                db.query(Experience)
                .filter(Experience.title == exp_data["title"])
                .first()
            )
            cat_id = categories_map.get(exp_data["category_name"])
            if not cat_id:
                continue
            venue_id = (
                venues_map.get(exp_data["venue_name"])
                if exp_data["venue_name"]
                else None
            )

            if not existing:
                existing = Experience(
                    host_id=exp_data["host_id"],
                    category_id=cat_id,
                    venue_id=venue_id,
                    title=exp_data["title"],
                    description=exp_data["description"],
                    cover_image_url=exp_data["cover_image_url"],
                    modality=exp_data["modality"],
                    status=exp_data["status"],
                    price=exp_data["price"],
                    min_capacity=exp_data["min_capacity"],
                    max_capacity=exp_data["max_capacity"],
                    reserved_slots=exp_data["reserved_slots"],
                    event_date=exp_data["event_date"],
                    duration_minutes=exp_data["duration_minutes"],
                    virtual_meeting_url=exp_data["virtual_meeting_url"],
                )
                db.add(existing)
                db.commit()
                db.refresh(existing)

            seeded.append(
                {
                    "id": existing.id,
                    "title": existing.title,
                    "modality": existing.modality.value,
                    "status": existing.status.value,
                    "price": existing.price,
                    "min_capacity": existing.min_capacity,
                    "max_capacity": existing.max_capacity,
                }
            )
        return seeded
    except Exception as e:
        db.rollback()
        print(f"[Seed Warning] No se pudieron inicializar experiencias: {e}")
        return []
    finally:
        db.close()


def seed_database() -> dict[str, Any]:
    """
    Puebla de forma idempotente roles, usuarios, categorías, locales geolocalizados
    y experiencias de prueba para todos los casos de uso del Sprint 1.

    Returns:
        dict[str, Any]: Diccionario resumen con todos los datos semilla insertados.
    """
    load_all_entities()
    roles = seed_default_roles()
    users = seed_default_users()
    categories = seed_default_categories()
    venues = seed_default_venues()
    experiences = seed_default_experiences()
    return {
        "status": "success",
        "message": "Datos semilla del Sprint 1 insertados correctamente.",
        "roles": roles,
        "users": users,
        "categories": categories,
        "venues": venues,
        "experiences": experiences,
    }


def reset_and_seed_database() -> dict[str, Any]:
    """
    Limpia la base de datos en cascada y genera de inmediato todos los datos semilla del Sprint 1.

    Returns:
        dict[str, Any]: Resumen completo de los datos semilla recreados.
    """
    reset_database()
    return seed_database()
