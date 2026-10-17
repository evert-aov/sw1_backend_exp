from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.experience.dto.experience_dto import VenueDTO, VenueCreateDTO
from app.experience.mapper.venue_mapper import VenueMapper
from app.experience.repository.venue_repository import VenueRepository


# Servicio para administración y consulta de establecimientos/locales comerciales
class VenueService:
    def __init__(self, db: Session):
        self.db = db
        self.venue_repo = VenueRepository(db)

    def get_all_venues(self, zone: Optional[str] = None) -> List[VenueDTO]:
        if zone:
            venues = self.venue_repo.get_by_zone(zone)
        else:
            venues = self.venue_repo.get_all()
        return [VenueMapper.to_dto(v) for v in venues]

    def get_venue_by_id(self, venue_id: int) -> VenueDTO:
        venue = self.venue_repo.get_by_id(venue_id)
        if not venue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El establecimiento con ID {venue_id} no fue encontrado",
            )
        return VenueMapper.to_dto(venue)

    def register_venue(self, owner_id: int, dto: VenueCreateDTO) -> VenueDTO:
        venue = VenueMapper.to_entity(dto, owner_id)
        created = self.venue_repo.create(venue)
        return VenueMapper.to_dto(created)
