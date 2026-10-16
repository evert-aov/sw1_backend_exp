from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import RoleChecker
from app.auth.entity.user import User
from app.experience.dto.experience_dto import CategoryDTO, CategoryCreateDTO
from app.experience.service.category_service import CategoryService

category_router = APIRouter(prefix="/categories", tags=["Categories Controller"])


@category_router.get("", response_model=List[CategoryDTO])
def list_categories(db: Session = Depends(get_db)):
    service = CategoryService(db)
    return service.get_all_categories()


@category_router.get("/{category_id}", response_model=CategoryDTO)
def get_category(category_id: int, db: Session = Depends(get_db)):
    service = CategoryService(db)
    return service.get_category_by_id(category_id)


@category_router.post("", response_model=CategoryDTO, status_code=status.HTTP_201_CREATED)
def create_category(
    dto: CategoryCreateDTO,
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["ADMIN", "HOST"])),
):
    service = CategoryService(db)
    return service.create_category(dto)


# Desacoplado; la gestión de establecimientos se trasladó al recurso independiente /api/venues (VenueController)
"""
@category_router.get("/venues", response_model=List[VenueDTO])
def list_venues(zone: Optional[str] = None, db: Session = Depends(get_db)):
    service = CategoryService(db)
    if zone:
        return service.get_venues_by_zone(zone)
    return service.get_all_venues()


@category_router.post("/venues", response_model=VenueDTO, status_code=status.HTTP_201_CREATED)
def create_venue(
    dto: VenueCreateDTO,
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["VENUE", "HOST", "ADMIN"])),
):
    service = CategoryService(db)
    return service.register_venue(current_user.id, dto)
"""
