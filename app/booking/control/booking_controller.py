from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.booking.dto.booking_dto import (
    BookingCreateDTO,
    BookingResponseDTO,
    TicketDTO,
)
from app.booking.service.booking_service import BookingService
from app.core.database import get_db
from app.core.security import get_current_active_user

booking_router = APIRouter(prefix="/bookings", tags=["Booking Controller (CU-06)"])


@booking_router.post(
    "",
    response_model=BookingResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una reserva de cupo (CU-06 / HU-06)",
    description="Inicia una reserva de cupos para una experiencia calculando comisiones escalonadas.",
)
def create_booking(
    dto: BookingCreateDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> BookingResponseDTO:
    """
    Inicia la reserva de cupos para una experiencia publicada (Sprint 2 - CU-06).

    Args:
        dto (BookingCreateDTO): ID de la experiencia y cantidad de entradas.
        db (Session): Sesión activa de base de datos.
        current_user (User): Usuario autenticado en sesión.

    Returns:
        BookingResponseDTO: Reserva registrada.
    """
    service = BookingService(db)
    return service.create_booking(user_id=current_user.id, dto=dto)


@booking_router.get(
    "/my-tickets",
    response_model=list[BookingResponseDTO],
    status_code=status.HTTP_200_OK,
    summary="Consultar historial de reservas y entradas con QR (HU-12)",
    description="Lista las reservas activas y pasadas del asistente junto con sus tickets QR.",
)
def get_my_tickets(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[BookingResponseDTO]:
    """
    Obtiene el historial de reservas y comprobantes QR del usuario (Sprint 2 - HU-12).

    Args:
        db (Session): Sesión activa de base de datos.
        current_user (User): Usuario autenticado en sesión.

    Returns:
        list[BookingResponseDTO]: Lista de reservas y tickets asociados.
    """
    service = BookingService(db)
    return service.get_user_bookings(user_id=current_user.id)


@booking_router.get(
    "/tickets/verify/{ticket_code}",
    response_model=TicketDTO,
    status_code=status.HTTP_200_OK,
    summary="Verificar validez de un ticket mediante código QR",
    description="Valida en puerta un código de entrada digital para control de asistencia.",
)
def verify_ticket(
    ticket_code: str,
    db: Annotated[Session, Depends(get_db)],
) -> TicketDTO:
    """
    Verifica y valida un ticket de ingreso mediante su código único QR (Sprint 2).

    Args:
        ticket_code (str): Código único del ticket.
        db (Session): Sesión activa de base de datos.

    Returns:
        TicketDTO: Estado del ticket verificado.
    """
    service = BookingService(db)
    return service.validate_ticket(ticket_code=ticket_code)
