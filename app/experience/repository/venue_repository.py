from typing import Optional, List
from sqlalchemy.orm import Session
from app.experience.entity.venue import Venue


# Repositorio para la entidad Venue: únicamente firmas de métodos
class VenueRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, venue_id: int) -> Optional[Venue]:
        # Buscar establecimiento por ID
        pass

    def create(self, venue: Venue) -> Venue:
        # Registrar nuevo local o espacio físico
        pass

    def get_by_zone(self, zone: str) -> List[Venue]:
        # Listar establecimientos por zona geográfica urbana
        pass

    def get_all(self) -> List[Venue]:
        # Listar todos los establecimientos registrados
        pass
