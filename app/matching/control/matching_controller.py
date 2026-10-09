from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.matching.dto.matching_dto import (
    MatchingApplicationDTO,
    MatchingGroupResponseDTO,
)
from app.matching.service.matching_service import MatchingAlgorithmService

matching_router = APIRouter(prefix="/matching", tags=["Matching Controller (CU-07)"])


@matching_router.post("/apply", response_model=MatchingGroupResponseDTO, status_code=status.HTTP_201_CREATED)
def apply_to_matching_group(dto: MatchingApplicationDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para unirse a un grupo de matching dinámico
    pass


@matching_router.get("/group/{experience_id}", response_model=MatchingGroupResponseDTO)
def get_matching_group_status(experience_id: int, db: Session = Depends(get_db)):
    # Firma de endpoint para consultar avance de quórum de un evento
    pass
