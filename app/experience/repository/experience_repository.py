from typing import Optional, List
from sqlalchemy.orm import Session
from app.experience.entity.experience import Experience
from app.experience.dto.experience_dto import ExperienceFilterDTO


# Repositorio para la entidad Experience: únicamente firmas de métodos
class ExperienceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, experience_id: int) -> Optional[Experience]:
        # Obtener experiencia por ID
        pass

    def create(self, experience: Experience) -> Experience:
        # Registrar nueva experiencia
        pass

    def update(self, experience: Experience) -> Experience:
        # Modificar datos de experiencia existente
        pass

    def filter(self, filters: ExperienceFilterDTO) -> List[Experience]:
        # Filtrar experiencias por categoría, modalidad, fecha, cercanía o precio
        pass

    def get_by_host(self, host_id: int) -> List[Experience]:
        # Listar experiencias publicadas por un anfitrión específico
        pass
