from typing import List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.experience.dto.experience_dto import CategoryDTO, CategoryCreateDTO
from app.experience.mapper.category_mapper import CategoryMapper
from app.experience.repository.category_repository import CategoryRepository


# Servicio para gestión de categorías y establecimientos asociados
class CategoryService:
    def __init__(self, db: Session):
        self.db = db
        self.category_repo = CategoryRepository(db)

    def get_all_categories(self) -> List[CategoryDTO]:
        categories = self.category_repo.get_all()
        return [CategoryMapper.to_dto(c) for c in categories]

    def get_category_by_id(self, category_id: int) -> CategoryDTO:
        category = self.category_repo.get_by_id(category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La categoría con ID {category_id} no fue encontrada",
            )
        return CategoryMapper.to_dto(category)

    def create_category(self, dto: CategoryCreateDTO) -> CategoryDTO:
        existing = self.category_repo.get_by_name(dto.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La categoría '{dto.name}' ya se encuentra registrada",
            )
        category = CategoryMapper.to_entity(dto)
        created = self.category_repo.create(category)
        return CategoryMapper.to_dto(created)

    # Desacoplado; implementados en app/experience/service/venue_service.py (VenueService)
    """
    def register_venue(self, owner_id: int, dto: VenueCreateDTO) -> VenueDTO:
        venue = Venue(
            owner_id=owner_id,
            name=dto.name.strip(),
            address=dto.address,
            city=dto.city or "Santa Cruz de la Sierra",
            zone=dto.zone,
            latitude=dto.latitude,
            longitude=dto.longitude,
            max_capacity=dto.max_capacity or 50,
            phone=dto.phone,
        )
        created = self.venue_repo.create(venue)
        return VenueDTO.model_validate(created)

    def get_venues_by_zone(self, zone: str) -> List[VenueDTO]:
        venues = self.venue_repo.get_by_zone(zone)
        return [VenueDTO.model_validate(v) for v in venues]

    def get_all_venues(self) -> List[VenueDTO]:
        venues = self.venue_repo.get_all()
        return [VenueDTO.model_validate(v) for v in venues]
    """
