from typing import List
from sqlalchemy.orm import Session
from app.experience.dto.experience_dto import CategoryDTO, CategoryCreateDTO, VenueDTO, VenueCreateDTO


# Servicio para gestión de categorías y establecimientos asociados
class CategoryService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_categories(self) -> List[CategoryDTO]:
        # Listar todas las categorías temáticas
        pass

    def create_category(self, dto: CategoryCreateDTO) -> CategoryDTO:
        # Registrar nueva categoría
        pass

    def register_venue(self, owner_id: int, dto: VenueCreateDTO) -> VenueDTO:
        # Registrar nuevo local o espacio comercial
        pass

    def get_venues_by_zone(self, zone: str) -> List[VenueDTO]:
        # Obtener locales en una zona urbana específica
        pass
