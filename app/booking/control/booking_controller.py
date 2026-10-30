from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.booking.dto.booking_dto import (
    BookingCreateDTO,
    BookingResponseDTO,
    TicketDTO,
    HostIncomeDTO,
    TicketScanDTO,
)
from app.booking.service.booking_service import BookingService
from app.core.database import get_db
from app.core.security import get_current_active_user, RoleChecker

booking_router = APIRouter(prefix="/bookings", tags=["Booking Controller (CU-05)"])


@booking_router.post(
    "",
    response_model=BookingResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una reserva de cupo (CU-05 / HU-06)",
    description="Inicia una reserva de cupos para una experiencia calculando comisiones escalonadas.",
)
def create_booking(
    dto: BookingCreateDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=64)
    ],
) -> BookingResponseDTO:
    """
    Inicia la reserva de cupos para una experiencia publicada (Sprint 2 - CU-05).

    Args:
        dto (BookingCreateDTO): ID de la experiencia y cantidad de entradas.
        db (Session): Sesión activa de base de datos.
        current_user (User): Usuario autenticado en sesión.

    Returns:
        BookingResponseDTO: Reserva registrada.
    """
    service = BookingService(db)
    return service.create_booking(
        user_id=current_user.id, dto=dto, idempotency_key=idempotency_key
    )


@booking_router.get(
    "/my-tickets",
    response_model=list[BookingResponseDTO],
    status_code=status.HTTP_200_OK,
    summary="Consultar historial de reservas y entradas con QR (HU-12)",
    description="Lista las reservas activas y pasadas del asistente junto con sus tickets QR.",
)
def get_my_tickets(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
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
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
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
    return service.validate_ticket(ticket_code=ticket_code, user_id=current_user.id)


@booking_router.get("/host-income", response_model=list[HostIncomeDTO])
def host_income(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["HOST", "VENUE"]))],
) -> list[HostIncomeDTO]:
    """Resume ingresos efectivos de las experiencias de la cuenta autenticada."""
    return BookingService(db).host_income(current_user.id)


@booking_router.get("/{booking_id}", response_model=BookingResponseDTO)
def get_booking(
    booking_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
) -> BookingResponseDTO:
    """Consulta el estado autorizado de una reserva después del checkout."""
    return BookingService(db).get_booking(booking_id, current_user.id)


@booking_router.post("/{booking_id}/cancel", response_model=BookingResponseDTO)
def cancel_booking(
    booking_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
) -> BookingResponseDTO:
    """Cancela una retención pendiente de la propia cuenta."""
    return BookingService(db).cancel_pending(booking_id, current_user.id)


@booking_router.post("/tickets/{ticket_id}/check-in", response_model=TicketDTO)
def check_in(
    ticket_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["HOST", "VENUE"]))],
) -> TicketDTO:
    """Consume una entrada una sola vez, con autorización del anfitrión."""
    return BookingService(db).check_in(ticket_id, current_user.id)


@booking_router.get("/tickets/{ticket_id}/qr", response_class=Response)
def ticket_qr(
    ticket_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ATTENDEE"]))],
) -> Response:
    """Entrega el QR autorizado sin enviar el payload a proveedores externos."""
    return Response(
        BookingService(db).ticket_qr(ticket_id, current_user.id),
        media_type="image/svg+xml",
        headers={"Cache-Control": "private, no-store"},
    )


@booking_router.post("/tickets/check-in", response_model=TicketDTO)
def scan_ticket(
    dto: TicketScanDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["HOST", "VENUE"]))],
) -> TicketDTO:
    """Valida lectura QR y registra ingreso exclusivamente para el anfitrión propietario."""
    return BookingService(db).scan_ticket(dto.code, current_user.id)
