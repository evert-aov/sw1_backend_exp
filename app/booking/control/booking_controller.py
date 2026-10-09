from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.booking.dto.booking_dto import (
    BookingCreateDTO,
    BookingResponseDTO,
    TicketDTO,
)
from app.booking.service.booking_service import BookingService

booking_router = APIRouter(prefix="/bookings", tags=["Booking Controller (CU-06)"])


@booking_router.post("", response_model=BookingResponseDTO, status_code=status.HTTP_201_CREATED)
def create_booking(dto: BookingCreateDTO, db: Session = Depends(get_db)):
    # Firma de endpoint para iniciar reserva de cupo
    pass


@booking_router.get("/my-tickets", response_model=List[BookingResponseDTO])
def get_my_tickets(db: Session = Depends(get_db)):
    # Firma de endpoint para ver historial de reservas y entradas con QR
    pass


@booking_router.get("/tickets/verify/{ticket_code}", response_model=TicketDTO)
def verify_ticket(ticket_code: str, db: Session = Depends(get_db)):
    # Firma de endpoint para control de acceso mediante QR
    pass
