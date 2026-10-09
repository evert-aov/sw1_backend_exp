from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.live.dto.live_dto import PostEventReportDTO
from app.live.service.smart_host_service import PostEventReportService

report_router = APIRouter(prefix="/reports", tags=["Post-Event Analytics Report Controller (CU-13)"])


@report_router.get("/{session_id}", response_model=PostEventReportDTO)
def get_post_event_report(session_id: int, db: Session = Depends(get_db)):
    # Firma de endpoint para consultar métricas y curvas de tiempo post-evento
    pass


@report_router.get("/{session_id}/pdf")
def download_report_pdf(session_id: int, db: Session = Depends(get_db)):
    # Firma de endpoint para descarga de reporte en PDF
    pass
