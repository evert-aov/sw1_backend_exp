from sqlalchemy.orm import Session
from app.live.dto.live_dto import (
    FramePayloadDTO,
    LiveMetricsDTO,
)


# Servicio de Visión por Computadora: procesamiento efímero en memoria RAM bajo estándar GDPR (CU-09)
class ComputerVisionService:
    def __init__(self, db: Session):
        self.db = db

    def process_frame_ephemeral(self, frame_dto: FramePayloadDTO) -> LiveMetricsDTO:
        # Inferencia en memoria RAM, cálculo de scores y descarte inmediato del frame
        pass

    def estimate_engagement_score(self, frame_data: bytes) -> float:
        # Calcular porcentaje de atención/entusiasmo facial
        pass

    def estimate_age_group(self, frame_data: bytes) -> str:
        # Estimar grupo etario predominante
        pass
