from sqlalchemy.orm import Session
from app.matching.dto.matching_dto import (
    MatchingApplicationDTO,
    MatchingGroupResponseDTO,
)


# Servicio para algoritmo de emparejamiento grupal y consolidación de quórum (CU-07)
class MatchingAlgorithmService:
    def __init__(self, db: Session):
        self.db = db

    def apply_for_matching(self, user_id: str, dto: MatchingApplicationDTO) -> MatchingGroupResponseDTO:
        # Postular usuario para completar quórum mínimo requerido
        pass

    def evaluate_quorum(self, group_id: str) -> bool:
        # Evaluar si el grupo completó los cupos requeridos antes de la fecha límite
        pass

    def trigger_quorum_confirmation(self, group_id: str) -> None:
        # Notificar a participantes y anfitrión la confirmación definitiva del evento
        pass
