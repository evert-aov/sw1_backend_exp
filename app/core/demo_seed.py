"""Datos ficticios por dataset, con propiedad correcta y sin pagos Stripe simulados."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
from uuid import UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from app.auth.entity.role import Role
from app.auth.entity.user import User
from app.auth.entity.user_role import UserRole
from app.auth.repository.role_repository import RoleRepository
from app.auth.repository.user_repository import UserRepository
from app.booking.dto.booking_dto import BookingCreateDTO
from app.booking.entity.booking import Booking
from app.booking.entity.ticket import Ticket
from app.booking.service.booking_service import BookingService, utc
from app.core.database import load_all_entities
from app.core.schema import validate_database_schema
from app.core.security import get_password_hash
from app.experience.dto.experience_dto import ExperienceCreateDTO, VenueCreateDTO
from app.experience.entity.category import Category
from app.experience.entity.experience import Experience, ExperienceStatusEnum
from app.experience.entity.venue import Venue
from app.experience.mapper.experience_mapper import ExperienceMapper
from app.experience.mapper.venue_mapper import VenueMapper
from app.matching.dto.matching_dto import MatchingApplicationDTO
from app.matching.entity.matching_group import MatchingGroup
from app.matching.entity.matching_member import MatchingMember
from app.matching.entity.search_log import SearchLog
from app.matching.service.matching_service import MatchingAlgorithmService
from app.notifications.entity import Notification

DEFAULT_DATASET = "roles-v2"
DEFAULT_DEMO_PASSWORD = "DemoRoles2026!"
SEED_NAMESPACE = UUID("67315ea4-2b8f-468e-91f9-1e7985664972")


class DemoSeedConflict(ValueError):
    """No se apropia de una cuenta o de un registro que no pertenece al dataset."""


def build_demo_plan(
    dataset: str = DEFAULT_DATASET, now: datetime | None = None
) -> dict:
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,23}", dataset):
        raise ValueError(
            "El dataset debe tener 1–24 caracteres: letras minúsculas, números y guiones"
        )
    now = utc(now or datetime.now(timezone.utc))
    day = now.replace(hour=22, minute=0, second=0, microsecond=0)

    def identity(kind, key):
        return str(uuid5(SEED_NAMESPACE, f"{dataset}:{kind}:{key}"))

    users = []
    for key, first, last, roles, interests in [
        ("admin", "Admin", "Demo", ["ADMIN"], []),
        ("host-cultura", "Camila", "Cultura", ["HOST"], ["cafe", "arte"]),
        ("host-talleres", "Mateo", "Talleres", ["HOST"], ["tecnologia", "arte"]),
        ("ana", "Ana", "Asistente", ["ATTENDEE"], ["cafe", "arte"]),
        ("luis", "Luis", "Asistente", ["ATTENDEE"], ["cafe", "musica"]),
        ("dual", "Alex", "Multirrol", ["HOST", "ATTENDEE"], ["cafe", "arte", "musica"]),
    ]:
        users.append(
            dict(
                key=key,
                id=identity("user", key),
                email=f"{key}.{dataset}@example.com",
                first_name=first,
                last_name=last,
                roles=roles,
                interests=interests,
            )
        )
    user_ids = {item["key"]: item["id"] for item in users}
    categories = [
        dict(key=key, id=identity("category", key), name=f"Demo [{dataset}] {name}")
        for key, name in [
            ("arte", "Arte"),
            ("cafe", "Café"),
            ("tecnologia", "Tecnología"),
            ("bienestar", "Bienestar"),
        ]
    ]
    category_ids = {item["key"]: item["id"] for item in categories}
    venues = []
    for key, owner, name, zone, capacity, lat, lon in [
        (
            "cultura",
            "host-cultura",
            "Espacio Cultura",
            "Equipetrol",
            30,
            -17.7605,
            -63.1958,
        ),
        (
            "talleres",
            "host-talleres",
            "Casa de Talleres",
            "Centro",
            20,
            -17.7833,
            -63.1821,
        ),
        ("terraza", "dual", "Terraza Creativa", "Urbarí", 12, -17.8032, -63.1964),
    ]:
        dto = VenueCreateDTO(
            name=f"{name} [{dataset}]",
            address=f"Dirección ficticia de prueba · {zone}",
            city="Santa Cruz de la Sierra",
            zone=zone,
            max_capacity=capacity,
            latitude=lat,
            longitude=lon,
        )
        venues.append(
            dict(
                key=key,
                id=identity("venue", key),
                owner_id=user_ids[owner],
                data=dto.model_dump(mode="json"),
            )
        )
    venue_ids = {item["key"]: item["id"] for item in venues}
    experiences = []
    for (
        key,
        host,
        venue,
        category,
        title,
        offset,
        price,
        minimum,
        maximum,
        modality,
        status,
    ) in [
        (
            "editable",
            "host-cultura",
            "cultura",
            "arte",
            "Taller de acuarela · editable",
            3,
            65,
            2,
            15,
            "IN_PERSON",
            "OPEN",
        ),
        (
            "confirmado",
            "host-cultura",
            "cultura",
            "cafe",
            "Encuentro gratuito de café · confirmado",
            5,
            0,
            2,
            8,
            "IN_PERSON",
            "OPEN",
        ),
        (
            "lleno",
            "host-cultura",
            "cultura",
            "arte",
            "Laboratorio creativo · sin cupos",
            6,
            0,
            2,
            2,
            "IN_PERSON",
            "OPEN",
        ),
        (
            "pendiente",
            "host-cultura",
            "cultura",
            "cafe",
            "Cata de café · pago pendiente",
            7,
            100,
            2,
            10,
            "IN_PERSON",
            "OPEN",
        ),
        (
            "grupo",
            "host-cultura",
            "cultura",
            "cafe",
            "Ruta del café · grupo por afinidad",
            14,
            120,
            3,
            12,
            "IN_PERSON",
            "OPEN",
        ),
        (
            "virtual",
            "host-talleres",
            None,
            "tecnologia",
            "Introducción a la fotografía móvil",
            8,
            50,
            2,
            20,
            "VIRTUAL",
            "OPEN",
        ),
        (
            "hibrido",
            "host-talleres",
            "talleres",
            "tecnologia",
            "Prototipado de ideas · híbrido",
            9,
            90,
            2,
            10,
            "HYBRID",
            "OPEN",
        ),
        (
            "dual",
            "dual",
            "terraza",
            "arte",
            "Dibujo al aire libre · multirrol",
            10,
            0,
            1,
            10,
            "IN_PERSON",
            "OPEN",
        ),
        (
            "cancelado",
            "host-talleres",
            "talleres",
            "arte",
            "Taller cancelado · sin reservas",
            11,
            80,
            2,
            10,
            "IN_PERSON",
            "CANCELLED",
        ),
        (
            "finalizado",
            "host-talleres",
            "talleres",
            "arte",
            "Encuentro finalizado · histórico",
            -3,
            0,
            2,
            10,
            "IN_PERSON",
            "FINISHED",
        ),
    ]:
        dto = ExperienceCreateDTO(
            title=f"[{dataset}] {title}",
            description="Experiencia ficticia para probar roles, lugares, reservas y estados del sistema.",
            category_id=category_ids[category],
            venue_id=venue_ids.get(venue),
            modality=modality,
            price=price,
            min_capacity=minimum,
            max_capacity=maximum,
            duration_minutes=120,
            event_date=day + timedelta(days=offset),
            virtual_meeting_url=f"https://example.com/demo/{dataset}/{key}"
            if modality != "IN_PERSON"
            else None,
        )
        experiences.append(
            dict(
                key=key,
                id=identity("experience", key),
                host_id=user_ids[host],
                status=status,
                data=dto.model_dump(mode="json"),
            )
        )
    event_ids = {item["key"]: item["id"] for item in experiences}
    bookings = [
        dict(
            user_id=user_ids[user],
            experience_id=event_ids[event],
            quantity=quantity,
            idempotency_key=f"seed:{dataset}:{key}",
        )
        for key, user, event, quantity in [
            ("ana-confirmado", "ana", "confirmado", 1),
            ("luis-confirmado", "luis", "confirmado", 1),
            ("ana-lleno", "ana", "lleno", 2),
            ("luis-pendiente", "luis", "pendiente", 1),
        ]
    ]
    searches = []
    for index in range(12):
        searches.append(
            dict(
                id=identity("search", str(index)),
                user_id=user_ids["ana" if index % 2 else "luis"],
                query_text=f"[DEMO {dataset}] bienestar sin oferta",
                category=next(
                    c["name"].lower() for c in categories if c["key"] == "bienestar"
                ),
                zone="plan 3000" if index < 8 else "pampa de la isla",
                found_results=False,
                dedupe_key=sha256(f"{dataset}:search:{index}".encode()).hexdigest(),
                search_filters={
                    "source": "demo-seed",
                    "dataset": dataset,
                    "max_price": 40 + (index % 4) * 10,
                    "date_from": (day + timedelta(days=20)).isoformat(),
                },
                created_at=now - timedelta(hours=index + 1),
            )
        )
    return dict(
        dataset=dataset,
        users=users,
        categories=categories,
        venues=venues,
        experiences=experiences,
        bookings=bookings,
        matching=[
            dict(user_id=user_ids[key], experience_id=event_ids["grupo"])
            for key in ["ana", "luis", "dual"]
        ],
        searches=searches,
    )


def _ensure(
    db: Session, model, identifier: str, values: dict, identity_fields: tuple[str, ...]
):
    existing = db.get(model, identifier)
    if existing:
        if any(getattr(existing, key) != values[key] for key in identity_fields):
            raise DemoSeedConflict(
                f"Conflicto de identidad en {model.__tablename__}. Usa otro --dataset; no se modificó el registro."
            )
        return existing, False
    item = model(id=identifier, **values)
    db.add(item)
    db.flush()
    return item, True


def populate_demo(db: Session, plan: dict, password: str) -> dict:
    """Usar dentro de la transacción externa creada por seed_demo_connection."""
    if db.join_transaction_mode != "create_savepoint" or not isinstance(
        db.get_bind(), Connection
    ):
        raise ValueError(
            "El seed exige una transacción PostgreSQL externa con savepoints"
        )
    connection = db.get_bind()
    if connection.dialect.name != "postgresql" or not connection.in_transaction():
        raise ValueError("El seed exige una transacción PostgreSQL externa activa")
    if not 8 <= len(password.encode()) <= 72:
        raise ValueError("La contraseña de prueba debe tener entre 8 y 72 bytes")
    roles = {
        name: RoleRepository(db).get_or_create_pending(name)
        for name in ["ADMIN", "HOST", "ATTENDEE"]
    }
    password_hash = None
    for item in plan["users"]:
        collision = db.scalar(select(User).where(User.email == item["email"]))
        if collision and collision.id != item["id"]:
            raise DemoSeedConflict(
                f"El correo de prueba {item['email']} ya pertenece a otra cuenta. Usa otro --dataset."
            )
        existing = db.get(User, item["id"])
        if not existing and password_hash is None:
            password_hash = get_password_hash(password)
        user, created = _ensure(
            db,
            User,
            item["id"],
            dict(
                email=item["email"],
                first_name=item["first_name"],
                last_name=item["last_name"],
                interests=item["interests"],
                is_active=True,
                hashed_password=password_hash,
                bio=f"Cuenta ficticia de prueba [{plan['dataset']}]",
            ),
            ("email",),
        )
        if created:
            for name in item["roles"]:
                db.add(UserRole(user_id=user.id, role_id=roles[name].id))
            db.flush()
        elif not user.is_active or set(
            UserRepository(db).get_user_roles(user.id)
        ) != set(item["roles"]):
            raise DemoSeedConflict(
                "Una cuenta del dataset cambió de estado o roles. Usa un nuevo --dataset para conservar esos cambios."
            )
    for item in plan["categories"]:
        collision = db.scalar(select(Category).where(Category.name == item["name"]))
        if collision and collision.id != item["id"]:
            raise DemoSeedConflict(
                "Una categoría de prueba ya existe con otro identificador. Usa otro --dataset."
            )
        _ensure(
            db,
            Category,
            item["id"],
            dict(
                name=item["name"],
                description=f"Categoría ficticia [{plan['dataset']}]",
                icon_name="sparkles",
            ),
            (),
        )
    for item in plan["venues"]:
        entity = VenueMapper.to_entity(VenueCreateDTO(**item["data"]), item["owner_id"])
        values = {
            key: getattr(entity, key)
            for key in [
                "owner_id",
                "name",
                "address",
                "city",
                "zone",
                "latitude",
                "longitude",
                "max_capacity",
                "phone",
            ]
        }
        _ensure(db, Venue, item["id"], values, ("owner_id",))
    for item in plan["experiences"]:
        entity = ExperienceMapper.to_entity(
            ExperienceCreateDTO(**item["data"]), item["host_id"]
        )
        values = {
            key: getattr(entity, key)
            for key in [
                "host_id",
                "category_id",
                "venue_id",
                "title",
                "description",
                "modality",
                "price",
                "min_capacity",
                "max_capacity",
                "duration_minutes",
                "virtual_meeting_url",
            ]
        }
        values.update(
            event_date=utc(entity.event_date).replace(tzinfo=None),
            status=ExperienceStatusEnum(item["status"]),
            reserved_slots=0,
            quorum_generation=0,
        )
        venue = db.get(Venue, values["venue_id"]) if values["venue_id"] else None
        if venue and (
            venue.owner_id != item["host_id"]
            or venue.max_capacity < values["max_capacity"]
        ):
            raise DemoSeedConflict(
                "El lugar del dataset cambió de propietario o capacidad. Usa otro --dataset."
            )
        _ensure(db, Experience, item["id"], values, ("host_id",))
    db.flush()
    db.commit()  # Libera el savepoint, sin confirmar la transacción externa.
    skipped = 0
    for item in plan["bookings"]:
        existing = db.scalar(
            select(Booking).where(
                Booking.user_id == item["user_id"],
                Booking.idempotency_key == item["idempotency_key"],
            )
        )
        if existing:
            if (
                existing.experience_id != item["experience_id"]
                or existing.quantity != item["quantity"]
            ):
                raise DemoSeedConflict(
                    "La clave de una reserva del dataset ya tiene otros datos"
                )
            continue
        experience = db.get(Experience, item["experience_id"])
        if utc(experience.event_date) <= datetime.now(
            timezone.utc
        ) or experience.status not in {
            ExperienceStatusEnum.OPEN,
            ExperienceStatusEnum.CONFIRMED,
        }:
            skipped += 1
            continue
        BookingService(db).create_booking(
            item["user_id"],
            BookingCreateDTO(
                experience_id=item["experience_id"], quantity=item["quantity"]
            ),
            item["idempotency_key"],
        )
    for item in plan["matching"]:
        existing = db.scalar(
            select(MatchingMember.id)
            .join(MatchingGroup)
            .where(
                MatchingGroup.experience_id == item["experience_id"],
                MatchingMember.user_id == item["user_id"],
            )
        )
        if existing:
            continue
        experience = db.get(Experience, item["experience_id"])
        if utc(experience.event_date) - timedelta(minutes=30) <= datetime.now(
            timezone.utc
        ) or experience.status not in {
            ExperienceStatusEnum.OPEN,
            ExperienceStatusEnum.CONFIRMED,
        }:
            skipped += 1
            continue
        MatchingAlgorithmService(db).apply_for_matching(
            item["user_id"], MatchingApplicationDTO(experience_id=item["experience_id"])
        )
    for item in plan["searches"]:
        values = {key: value for key, value in item.items() if key != "id"}
        _ensure(db, SearchLog, item["id"], values, ("dedupe_key",))
    db.commit()
    event_ids = [item["id"] for item in plan["experiences"]]
    bookings = db.scalars(
        select(Booking).where(Booking.experience_id.in_(event_ids))
    ).all()
    return dict(
        dataset=plan["dataset"],
        users=len(plan["users"]),
        venues=len(plan["venues"]),
        experiences=len(event_ids),
        bookings=len(bookings),
        tickets=len(
            db.scalars(
                select(Ticket.id)
                .join(Booking)
                .where(Booking.experience_id.in_(event_ids))
            ).all()
        ),
        matching_members=len(
            db.scalars(
                select(MatchingMember.id)
                .join(MatchingGroup)
                .where(MatchingGroup.experience_id.in_(event_ids))
            ).all()
        ),
        notifications=len(
            db.scalars(
                select(Notification.id).where(Notification.experience_id.in_(event_ids))
            ).all()
        ),
        synthetic_searches=len(plan["searches"]),
        skipped_interactions=skipped,
        accounts=[
            dict(email=item["email"], roles=item["roles"]) for item in plan["users"]
        ],
    )


def seed_demo_connection(
    connection: Connection, plan: dict, password: str = DEFAULT_DEMO_PASSWORD
) -> dict:
    if connection.dialect.name != "postgresql" or not connection.in_transaction():
        raise ValueError("Usa una conexión PostgreSQL dentro de engine.begin()")
    load_all_entities()
    validate_database_schema(connection)
    # Comparte el orden de bloqueo con la administración de roles.
    connection.execute(text("SELECT pg_advisory_xact_lock(2026102601)"))
    with Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        report = populate_demo(db, plan, password)
        db.commit()
        return report
