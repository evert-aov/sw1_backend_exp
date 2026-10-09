from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.experience.dto.experience_dto import (
    CategoryDTO,
    CategoryCreateDTO,
    VenueDTO,
    VenueCreateDTO,
)
from app.experience.service.category_service import CategoryService

category_router = APIRouter(prefix="/categories", tags=["Categories & Venues Controller"])


@category_router.get("", response_model=List[CategoryDTO])
def list_categories(db: Session = Depends(get_db)):
    # Firma de endpoint para listar categorías
    pass


@category_router.post("", response_model=CategoryDTO, status_code=status.HTTP_201_CREATED)
def create_category(dto: CategoryCreateDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para registrar nueva categoría
    pass


@category_router.post("/venues", response_model=VenueDTO, status_code=status.HTTP_201_CREATED)
def create_venue(dto: VenueCreateDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para registrar local físico
    pass
