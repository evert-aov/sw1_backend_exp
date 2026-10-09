from typing import List
from sqlalchemy.orm import Session
from app.experience.dto.experience_dto import (
    ExperienceCreateDTO,
    ExperienceUpdateDTO,
    ExperienceFilterDTO,
    ExperienceResponseDTO,
    CatalogResponseDTO,
)


# Servicio para gestión de experiencias, cálculo de aforos y validación de modalidades (CU-03, CU-04, CU-05)
class ExperienceService:
    def __init__(self, db: Session):
        self.db = db

    def create_experience(self, host_id: int, dto: ExperienceCreateDTO) -> ExperienceResponseDTO:
        # Publicar nueva experiencia validando aforo mínimo, cupo límite y modalidad
        pass

    def update_experience(self, experience_id: int, host_id: int, dto: ExperienceUpdateDTO) -> ExperienceResponseDTO:
        # Actualizar datos de una experiencia
        pass

    def get_experience_by_id(self, experience_id: int) -> ExperienceResponseDTO:
        # Consultar detalle completo de una experiencia
        pass

    def search_catalog(self, filters: ExperienceFilterDTO) -> CatalogResponseDTO:
        # Explorar y filtrar catálogo por cercanía, fecha, categoría y modalidad
        pass

    def check_quorum(self, experience_id: int) -> bool:
        # Validar si se alcanzó el aforo mínimo para confirmar el evento
        pass
