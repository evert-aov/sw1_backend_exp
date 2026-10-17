from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import RoleChecker, get_current_active_user
from app.auth.entity.user import User
from app.experience.entity.experience import ExperienceStatusEnum
from app.experience.dto.experience_dto import (
    ExperienceCreateDTO,
    ExperienceUpdateDTO,
    ExperienceFilterDTO,
    ExperienceResponseDTO,
    CatalogResponseDTO,
)
from app.experience.service.experience_service import ExperienceService

experience_router = APIRouter(prefix="/experiences", tags=["Experience Controller (CU-03, CU-04, CU-05)"])


@experience_router.post("", response_model=ExperienceResponseDTO, status_code=status.HTTP_201_CREATED)
def create_experience(
    dto: ExperienceCreateDTO,
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["HOST", "VENUE", "ADMIN"])),
):
    service = ExperienceService(db)
    return service.create_experience(host_id=current_user.id, dto=dto)


@experience_router.get("/catalog", response_model=CatalogResponseDTO)
def search_catalog(filters: ExperienceFilterDTO = Depends(), db: Session = Depends(get_db)):
    service = ExperienceService(db)
    return service.search_catalog(filters)


@experience_router.get("/me/hosted", response_model=List[ExperienceResponseDTO])
def get_my_hosted_experiences(
    status: Optional[ExperienceStatusEnum] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ExperienceService(db)
    return service.get_my_hosted_experiences(host_id=current_user.id, status=status)


@experience_router.get("/{experience_id}", response_model=ExperienceResponseDTO)
def get_experience_detail(experience_id: int, db: Session = Depends(get_db)):
    service = ExperienceService(db)
    return service.get_experience_by_id(experience_id)


@experience_router.put("/{experience_id}", response_model=ExperienceResponseDTO)
def update_experience(
    experience_id: int,
    dto: ExperienceUpdateDTO,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ExperienceService(db)
    return service.update_experience(experience_id=experience_id, host_id=current_user.id, dto=dto)


@experience_router.patch("/{experience_id}/cancel", response_model=ExperienceResponseDTO)
def cancel_experience(
    experience_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    service = ExperienceService(db)
    return service.cancel_experience(experience_id=experience_id, host_id=current_user.id)
