from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import RoleChecker
from app.auth.entity.user import User
from app.experience.dto.experience_dto import VenueDTO, VenueCreateDTO
from app.experience.service.venue_service import VenueService

venue_router = APIRouter(prefix="/venues", tags=["Venues Controller"])


@venue_router.get("", response_model=List[VenueDTO], summary="Listar todos los establecimientos")
def list_venues(zone: Optional[str] = None, db: Session = Depends(get_db)):
    service = VenueService(db)
    return service.get_all_venues(zone=zone)


@venue_router.get("/{venue_id}", response_model=VenueDTO, summary="Obtener detalles de un establecimiento por ID")
def get_venue(venue_id: int, db: Session = Depends(get_db)):
    service = VenueService(db)
    return service.get_venue_by_id(venue_id)


@venue_router.post(
    "",
    response_model=VenueDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un nuevo establecimiento",
)
def create_venue(
    dto: VenueCreateDTO,
    db: Session = Depends(get_db),
    current_user: User = Depends(RoleChecker(["VENUE", "HOST", "ADMIN"])),
):
    service = VenueService(db)
    return service.register_venue(current_user.id, dto)
