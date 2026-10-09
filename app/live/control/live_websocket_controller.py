from fastapi import APIRouter, WebSocket, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.live.dto.live_dto import (
    LiveSessionCreateDTO,
    LiveMetricsDTO,
    ConsentDTO,
)
from app.live.service.computer_vision_service import ComputerVisionService
from app.live.service.smart_host_service import SmartHostService

live_router = APIRouter(prefix="/live", tags=["Live & WebSocket Controller (CU-09, CU-10, CU-11, CU-12)"])


@live_router.post("/session", status_code=status.HTTP_201_CREATED)
def start_live_session(dto: LiveSessionCreateDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para iniciar sesión en vivo
    pass


@live_router.post("/consent", status_code=status.HTTP_200_OK)
def record_gdpr_consent(dto: ConsentDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para registrar consentimiento GDPR del asistente
    pass


@live_router.websocket("/ws/{session_id}")
async def live_stream_websocket(websocket: WebSocket, session_id: int):
    # Firma de endpoint WebSocket para ingesta de frames y broadcast de métricas
    pass
