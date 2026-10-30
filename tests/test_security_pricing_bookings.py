"""Regresión de fallos de seguridad, dinero y límites de reserva, sin simular PostgreSQL real."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.auth.dto.auth_dto import RegisterDTO, RoleSwitchDTO
from app.auth.entity.revoked_token import RevokedToken
from app.auth.service.auth_service import AuthService
from app.auth.service.profile_service import ProfileService
from app.booking.dto.booking_dto import BookingCreateDTO
from app.booking.entity.booking import Booking, BookingStatusEnum
from app.booking.service.booking_service import BookingService
from app.core.pricing import quote_price
from app.core.security import create_access_token, decode_token, revoke_token
from app.core.system_controller import require_maintenance_access
from app.core.config import settings


@pytest.mark.parametrize("role", ["ADMIN", "admin", " ADMIN ", "SUPERUSER"])
def test_public_registration_cannot_assign_admin(role):
    """Rechaza elevación de privilegios antes de escribir o consultar cuentas."""
    session = MagicMock()
    with pytest.raises(HTTPException) as error:
        AuthService(session).register(RegisterDTO(first_name="Prueba", email="audit@example.com", password="password123", role=role))
    assert error.value.status_code == 400
    session.query.assert_not_called()
    session.commit.assert_not_called()


def test_role_change_rejects_privileged_and_unknown_fields():
    """El contrato no acepta ADMIN ni un arreglo arbitrario de roles."""
    for payload in ({"role": "ADMIN"}, {"role": "HOST", "roles": ["ADMIN"]}):
        with pytest.raises(ValidationError):
            RoleSwitchDTO(**payload)
    session = MagicMock()
    with pytest.raises(HTTPException):
        ProfileService(session).switch_public_role(str(uuid4()), "ADMIN")
    session.query.assert_not_called()


def test_maintenance_is_disabled_even_for_administrator():
    """Ser administrador no habilita por sí mismo rutas destructivas."""
    with patch.object(settings, "ENABLE_MAINTENANCE_ENDPOINTS", False):
        with pytest.raises(HTTPException) as error:
            require_maintenance_access(SimpleNamespace(id=str(uuid4())))
    assert error.value.status_code == 404


def test_logout_persists_fingerprint_not_raw_token():
    """El SQL conserva huella y vencimiento; un fallo de persistencia no se oculta."""
    token = create_access_token(str(uuid4()))
    session = MagicMock()
    revoke_token(token, session)
    parameters = session.execute.call_args.args[0].compile().params
    assert parameters["token_hash"] == sha256(token.encode()).hexdigest()
    assert token not in parameters.values()
    assert parameters["expires_at"] > datetime.now(timezone.utc)
    session.commit.assert_called_once()
    session.execute.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError):
        revoke_token(token, session)
    session.rollback.assert_called_once()


def test_auth_checks_shared_revocation_and_invalid_signature_before_database():
    """Un JWT revocado no autoriza; uno mal firmado no consulta la tabla."""
    token = create_access_token(str(uuid4()))
    session = MagicMock()
    session.get.return_value = RevokedToken(token_hash="x")
    with pytest.raises(HTTPException) as error:
        decode_token(token, session)
    assert error.value.status_code == 401
    session.get.reset_mock()
    with pytest.raises(HTTPException):
        decode_token("invalid.jwt.token", session)
    session.get.assert_not_called()


@pytest.mark.parametrize("price,rate,fee", [
    ("0", "0.10", "0.00"), ("99.99", "0.10", "10.00"),
    ("100", "0.08", "8.00"), ("300", "0.08", "24.00"),
    ("300.01", "0.05", "15.00"), ("0.05", "0.10", "0.01"),
])
def test_commission_boundaries_balance_for_multiple_tickets(price, rate, fee):
    """Conserva límites de escalones y balance exacto después del redondeo por entrada."""
    quote = quote_price(price, 3)
    assert quote.commission_rate == Decimal(rate)
    assert quote.fee_per_ticket == Decimal(fee)
    assert quote.total_amount == quote.platform_fee + quote.host_payout
    assert quote.total_amount == quote.unit_price * 3


@pytest.mark.parametrize("price", ["-0.01", "NaN", "Infinity"])
def test_invalid_money_is_rejected(price):
    """No cotiza importes negativos o no finitos."""
    with pytest.raises(ValueError):
        quote_price(price)


def test_booking_rejects_bad_uuid_before_sql():
    """Un identificador incorrecto produce 422, no un error del driver PostgreSQL."""
    session = MagicMock()
    with pytest.raises(HTTPException) as error:
        BookingService(session).create_booking("user", BookingCreateDTO(experience_id="bad"), "test-key-123")
    assert error.value.status_code == 422
    session.query.assert_not_called()


def booking_session(existing=None, holds=0, event=None):
    """Prepara dependencias de consulta para probar decisiones de negocio, no bloqueos reales."""
    session = MagicMock()
    user_query, existing_query, event_query = MagicMock(), MagicMock(), MagicMock()
    user_query.filter.return_value.with_for_update.return_value.first.return_value = SimpleNamespace(is_active=True)
    existing_query.filter.return_value.first.return_value = existing
    event_query.filter.return_value.populate_existing.return_value = event_query.filter.return_value
    event_query.filter.return_value.with_for_update.return_value.first.return_value = event or SimpleNamespace(
        id=str(uuid4()), status="OPEN", event_date=datetime.now(timezone.utc) + timedelta(days=1),
        reserved_slots=1, max_capacity=2, price=Decimal("100.00"), min_capacity=2,
    )
    session.query.side_effect = [user_query, existing_query, event_query]
    session.scalar.return_value = holds
    return session


def test_last_slot_accounts_for_other_active_holds():
    """Una retención ajena impide reservar un cupo ya comprometido."""
    session = booking_session(holds=1)
    with pytest.raises(HTTPException) as error:
        BookingService(session).create_booking(str(uuid4()), BookingCreateDTO(experience_id=str(uuid4())), "test-key-123")
    assert error.value.status_code == 409
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_same_idempotency_key_with_different_request_is_conflict():
    """Una clave no puede reutilizarse para cambiar experiencia o cantidad."""
    existing = SimpleNamespace(experience_id=str(uuid4()), quantity=1)
    session = booking_session(existing=existing)
    with pytest.raises(HTTPException) as error:
        BookingService(session).create_booking(str(uuid4()), BookingCreateDTO(experience_id=str(uuid4())), "same-key-123")
    assert error.value.status_code == 409
    session.add.assert_not_called()


def test_paid_booking_cannot_be_cancelled_as_a_hold():
    """No simula un reembolso cambiando un estado de SQL sin pasar por el proveedor."""
    session = MagicMock()
    user_id = str(uuid4())
    booking = SimpleNamespace(user_id=user_id, status=BookingStatusEnum.PAID)
    session.query.return_value.filter.return_value.populate_existing.return_value = session.query.return_value.filter.return_value
    session.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = booking
    with pytest.raises(HTTPException) as error:
        BookingService(session).cancel_pending(str(uuid4()), user_id)
    assert error.value.status_code == 409
    session.commit.assert_not_called()


def test_booking_lookup_hides_other_buyers():
    """El comprador no obtiene una reserva ajena aunque conozca su ID."""
    service = BookingService(MagicMock())
    with patch.object(service, "_load", return_value=SimpleNamespace(user_id=str(uuid4()))):
        with pytest.raises(HTTPException) as error:
            service.get_booking(str(uuid4()), str(uuid4()))
    assert error.value.status_code == 403
