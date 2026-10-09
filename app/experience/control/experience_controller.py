from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
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
def create_experience(dto: ExperienceCreateDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para publicar una experiencia
    pass


@experience_router.get("/catalog", response_model=CatalogResponseDTO)
def search_catalog(filters: ExperienceFilterDTO = Depends(), db: Session = Depends(get_db)):
    # Firma de endpoint para explorar y filtrar catálogo
    pass


@experience_router.get("/{experience_id}", response_model=ExperienceResponseDTO)
def get_experience_detail(experience_id: int, db: Session = Depends(get_db)):
    # Firma de endpoint para ver detalle de experiencia
    pass


@experience_router.put("/{experience_id}", response_model=ExperienceResponseDTO)
def update_experience(experience_id: int, dto: ExperienceUpdateDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para editar experiencia
    pass
