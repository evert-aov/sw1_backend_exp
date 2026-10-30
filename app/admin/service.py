"""Consultas de plataforma y asignación transaccional de roles."""

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload, selectinload
from app.admin.dto import OverviewDTO
from app.auth.dto.auth_dto import ProfileDTO
from app.auth.entity.user import User
from app.auth.entity.role import Role
from app.auth.entity.user_role import UserRole
from app.auth.repository.role_repository import RoleRepository
from app.auth.repository.user_repository import UserRepository
from app.auth.service.profile_service import ProfileService
from app.booking.entity.booking import Booking, BookingStatusEnum
from app.experience.entity.experience import Experience
from app.experience.entity.venue import Venue
from app.experience.dto.experience_dto import ExperienceResponseDTO
from app.experience.mapper.experience_mapper import ExperienceMapper


def get_overview(db: Session) -> OverviewDTO:
    def count(model, *filters):
        return db.scalar(select(func.count()).select_from(model).where(*filters)) or 0

    def role_count(roles):
        return (
            db.scalar(
                select(func.count(func.distinct(UserRole.user_id)))
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name.in_(roles))
            )
            or 0
        )

    return OverviewDTO(
        users=count(User),
        active_users=count(User, User.is_active.is_(True)),
        hosts=role_count(["HOST", "VENUE"]),
        attendees=role_count(["ATTENDEE"]),
        venues=count(Venue),
        experiences=count(Experience),
        paid_bookings=count(Booking, Booking.status == BookingStatusEnum.PAID),
    )


def get_experiences(
    db: Session, skip: int = 0, limit: int = 25
) -> list[ExperienceResponseDTO]:
    items = (
        db.query(Experience)
        .options(
            joinedload(Experience.host),
            joinedload(Experience.venue),
            joinedload(Experience.category),
            selectinload(
                Experience.bookings.and_(Booking.status == BookingStatusEnum.PENDING)
            ),
        )
        .order_by(Experience.created_at.desc(), Experience.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [ExperienceMapper.to_response_dto(item) for item in items]


def assign_roles(
    db: Session, actor_id: str, user_id: str, roles: list[str]
) -> ProfileDTO:
    """Serializa asignaciones; no permite revocarse ADMIN ni dejar la plataforma sin administrador."""
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(2026102601)"))
        if "ADMIN" not in UserRepository(db).get_user_roles(actor_id):
            raise HTTPException(
                status_code=403, detail="La cuenta ya no tiene el rol ADMIN"
            )
        user = db.query(User).filter(User.id == user_id).with_for_update().first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        if actor_id == user_id and "ADMIN" not in roles:
            raise HTTPException(
                status_code=409, detail="No puedes quitarte tu propio rol ADMIN"
            )
        current_roles = UserRepository(db).get_user_roles(user_id)
        if "ADMIN" in current_roles and "ADMIN" not in roles and user.is_active:
            other_admin = db.scalar(
                select(User.id)
                .join(UserRole)
                .join(Role)
                .where(
                    Role.name == "ADMIN", User.is_active.is_(True), User.id != user_id
                )
                .limit(1)
            )
            if not other_admin:
                raise HTTPException(
                    status_code=409,
                    detail="Debe existir al menos un administrador activo",
                )
        selected = [
            RoleRepository(db).get_or_create_pending(name)
            for name in sorted(set(roles))
        ]
        db.query(UserRole).filter(UserRole.user_id == user_id).delete(
            synchronize_session=False
        )
        for role in selected:
            db.add(UserRole(user_id=user_id, role_id=role.id))
        db.commit()
        return ProfileService(db).get_profile(user_id)
    except Exception:
        db.rollback()
        raise
