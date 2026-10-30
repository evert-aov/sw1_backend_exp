"""Administración de plataforma; requiere ADMIN consultado en PostgreSQL."""

from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import RoleChecker, get_current_active_user
from app.auth.entity.user import User
from app.auth.dto.auth_dto import ProfileDTO
from app.experience.dto.experience_dto import ExperienceResponseDTO
from app.admin.dto import AdminRolesDTO, OverviewDTO
from app.admin.service import assign_roles, get_overview, get_experiences

admin_router = APIRouter(
    prefix="/admin",
    tags=["Administración de plataforma"],
    dependencies=[Depends(RoleChecker(["ADMIN"]))],
)


@admin_router.get("/overview", response_model=OverviewDTO)
def overview(db: Annotated[Session, Depends(get_db)]) -> OverviewDTO:
    return get_overview(db)


@admin_router.get("/experiences", response_model=list[ExperienceResponseDTO])
def platform_experiences(
    db: Annotated[Session, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
) -> list[ExperienceResponseDTO]:
    return get_experiences(db, skip, limit)


@admin_router.put("/users/{user_id}/roles", response_model=ProfileDTO)
def update_roles(
    user_id: str,
    dto: AdminRolesDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> ProfileDTO:
    return assign_roles(db, current_user.id, user_id, dto.roles)
