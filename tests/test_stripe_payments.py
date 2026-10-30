"""Reglas financieras con entidades reales y transporte Stripe controlado; sin simular PG."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import hmac
import json
import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
import pytest
import stripe
from app.booking.entity.booking import Booking, BookingStatusEnum
from app.booking.entity.payment import Payment, PaymentStatusEnum
from app.booking.service.stripe_gateway import StripeGateway
from app.booking.service.stripe_service import StripeService, minor_units
from app.core.config import settings
from app.core.database import load_all_entities
from app.experience.entity.experience import Experience, ExperienceStatusEnum


@pytest.fixture
def flow():
    load_all_entities()
    now = datetime.now(timezone.utc)
    event = Experience(id=str(uuid4()), host_id=str(uuid4()), status=ExperienceStatusEnum.OPEN,
                       event_date=now + timedelta(days=1), reserved_slots=0, min_capacity=2, max_capacity=4)
    booking = Booking(id=str(uuid4()), user_id=str(uuid4()), experience=event, experience_id=event.id,
                      quantity=2, total_amount=Decimal("200.00"), platform_fee=Decimal("16.00"),
                      host_payout=Decimal("184.00"), currency="BOB", status=BookingStatusEnum.PENDING,
                      expires_at=now + timedelta(minutes=15), created_at=now, tickets=[])
    payment = Payment(id=str(uuid4()), booking=booking, booking_id=booking.id, amount=booking.total_amount,
                      currency="BOB", status=PaymentStatusEnum.PENDING, stripe_checkout_session_id="cs_test_known", payment_metadata={})
    remote = {"id": "cs_test_known", "client_reference_id": booking.id, "payment_status": "paid",
              "payment_intent": "pi_test_known", "amount_total": 20000, "currency": "bob", "status": "complete"}
    service = StripeService(MagicMock(), gateway=MagicMock())
    service._locked = MagicMock(return_value=(booking, event, payment))
    return service, booking, event, payment, remote


def test_signature_verification_uses_unmodified_body_before_database():
    payload = json.dumps({"id": "evt_signed", "object": "event", "type": "other", "data": {"object": {"id": "obj_1"}}}).encode()
    timestamp = int(time.time())
    secret = "whsec_only_test_secret"
    digest = hmac.new(secret.encode(), str(timestamp).encode() + b"." + payload, sha256).hexdigest()
    with patch.object(settings, "STRIPE_WEBHOOK_SECRET", secret):
        event = StripeGateway().verify_event(payload, f"t={timestamp},v1={digest}")
        assert event.get("id") == "evt_signed"
        assert event.get("data", {}).get("object", {}).get("id") == "obj_1"
        for body, signature in [(payload + b" ", f"t={timestamp},v1={digest}"), (payload, ""), (payload, f"t={timestamp - 600},v1={digest}")]:
            with pytest.raises(HTTPException) as error:
                StripeGateway().verify_event(body, signature)
            assert error.value.status_code == 400


@pytest.mark.parametrize("method,path,args,resource", [
    ("create_checkout", "checkout.sessions.create", ({"mode": "payment"}, "checkout:test"), stripe.checkout.Session),
    ("retrieve_checkout", "checkout.sessions.retrieve", ("cs_test",), stripe.checkout.Session),
    ("expire_checkout", "checkout.sessions.expire", ("cs_test",), stripe.checkout.Session),
    ("refund", "refunds.create", ("pi_test", "refund:test"), stripe.Refund),
    ("retrieve_refund", "refunds.retrieve", ("re_test",), stripe.Refund),
    ("retrieve_current_account", "accounts.retrieve_current", (), stripe.Account),
])
def test_gateway_converts_real_sdk_resources_recursively(method, path, args, resource):
    client = MagicMock()
    endpoint = client.v1
    for part in path.split("."):
        endpoint = getattr(endpoint, part)
    endpoint.return_value = resource.construct_from({"id": "resource_test", "metadata": {"booking_id": "booking_test"}}, None)
    with patch.object(StripeGateway, "_client", return_value=client):
        result = getattr(StripeGateway(), method)(*args)
    assert result.get("id") == "resource_test"
    assert result.get("metadata", {}).get("booking_id") == "booking_test"
    assert result.get("absent") is None


def test_checkout_service_accepts_real_sdk_session_through_gateway(flow):
    service, booking, _, payment, _ = flow
    payment.stripe_checkout_session_id = None
    payment.payment_metadata = {"checkout_params": {"mode": "payment"}}
    service.gateway = StripeGateway()
    client = MagicMock()
    client.v1.checkout.sessions.create.return_value = stripe.checkout.Session.construct_from({
        "id": "cs_real_sdk", "url": "https://checkout.stripe.com/c/pay/test", "status": "open",
    }, None)
    with patch.object(StripeGateway, "_client", return_value=client):
        result = service.create_checkout_session(booking.id, booking.user_id)
    assert result.stripe_session_id == payment.stripe_checkout_session_id == "cs_real_sdk"
    client.v1.checkout.sessions.create.assert_called_once_with(
        {"mode": "payment"}, options={"idempotency_key": f"checkout:{payment.id}"},
    )
    assert service.db.commit.call_count == 2


@pytest.mark.parametrize("amount,currency,expected", [("0.05", "BOB", 5), ("123.45", "USD", 12345), ("100", "EUR", 10000)])
def test_minor_units_are_exact(amount, currency, expected):
    assert minor_units(amount, currency) == expected


@pytest.mark.parametrize("amount,currency", [("0", "BOB"), ("-1", "USD"), ("1.001", "BOB"), ("NaN", "BOB"), ("100", "JPY")])
def test_invalid_or_unsupported_money_is_rejected(amount, currency):
    with pytest.raises(HTTPException):
        minor_units(amount, currency)


def test_verified_payment_generates_exactly_one_ticket_per_seat(flow):
    service, booking, event, payment, remote = flow
    assert service._apply_session(remote, booking, event, payment) == "PAID"
    assert booking.status == BookingStatusEnum.PAID
    assert event.reserved_slots == 2
    assert event.status == ExperienceStatusEnum.CONFIRMED
    assert service.db.add.call_count == 2
    assert service._apply_session(remote, booking, event, payment) == "ALREADY_PAID"
    assert service.db.add.call_count == 2
    service.db.commit.assert_not_called()  # El webhook confirma evento/pago/tickets conjuntamente.


@pytest.mark.parametrize("field,value", [("amount_total", 1), ("currency", "usd"), ("client_reference_id", "another-booking"), ("id", "cs_other"), ("payment_intent", None)])
def test_provider_mismatch_never_issues_entries(flow, field, value):
    service, booking, event, payment, remote = flow
    remote[field] = value
    with pytest.raises(HTTPException):
        service._apply_session(remote, booking, event, payment)
    assert booking.status == BookingStatusEnum.PENDING
    assert event.reserved_slots == 0
    service.db.add.assert_not_called()


def test_late_payment_records_durable_refund_without_occupying_seats(flow):
    service, booking, event, payment, remote = flow
    booking.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert service._apply_session(remote, booking, event, payment) == "REFUND_PENDING"
    assert payment.status == PaymentStatusEnum.SUCCEEDED
    assert payment.payment_metadata["refund_requested"] is True
    assert booking.status == BookingStatusEnum.CANCELLED
    assert event.reserved_slots == 0
    service.db.add.assert_not_called()


def test_expiration_or_failure_delivered_after_payment_does_not_reverse_it(flow):
    service, booking, event, payment, remote = flow
    service._apply_session(remote, booking, event, payment)
    service._apply_session({**remote, "payment_status": "unpaid", "status": "expired"}, booking, event, payment, failed=True)
    assert payment.status == PaymentStatusEnum.SUCCEEDED
    assert booking.status == BookingStatusEnum.PAID
    assert event.reserved_slots == 2


def test_duplicate_webhook_does_not_repeat_business_effects(flow):
    service, booking, event, payment, remote = flow
    service.gateway.verify_event.return_value = {"id": "evt_duplicate", "type": "checkout.session.completed", "data": {"object": remote}}
    service.db.scalar.return_value = None
    assert service.handle_webhook_event(b"raw", "signature")["outcome"] == "DUPLICATE"
    service._locked.assert_not_called()
    service.db.add.assert_not_called()


def test_webhook_rolls_back_inbox_and_payment_if_tickets_cannot_be_written(flow):
    service, booking, event, payment, remote = flow
    service.gateway.verify_event.return_value = {"id": "evt_atomic", "type": "checkout.session.completed", "data": {"object": remote}}
    service.db.scalar.return_value = "evt_atomic"
    service.payments.get_by_stripe_session = MagicMock(return_value=payment)
    service.db.add.side_effect = RuntimeError("ticket write failed")
    with pytest.raises(RuntimeError, match="ticket write failed"):
        service.handle_webhook_event(b"raw", "signature")
    service.db.rollback.assert_called_once()
    service.db.commit.assert_not_called()


def test_checkout_and_status_reject_another_buyer_before_stripe(flow):
    service, booking, event, payment, remote = flow
    for method in (service.create_checkout_session, service.reconcile_booking):
        with pytest.raises(HTTPException) as error:
            method(booking.id, str(uuid4()))
        assert error.value.status_code == 403
    service.gateway.create_checkout.assert_not_called()
    service.gateway.retrieve_checkout.assert_not_called()


def test_checkout_retries_use_durable_parameters_and_provider_key(flow):
    service, booking, event, payment, remote = flow
    payment.stripe_checkout_session_id = None
    payment.payment_metadata = {"checkout_params": {"immutable": "stored parameters"}}
    service.gateway.create_checkout.return_value = {"id": "cs_created", "url": "https://checkout.stripe.com/c/pay/test"}
    result = service.create_checkout_session(booking.id, booking.user_id)
    assert result.stripe_session_id == "cs_created"
    service.gateway.create_checkout.assert_called_once_with({"immutable": "stored parameters"}, f"checkout:{payment.id}")
    assert service.db.commit.call_count == 2


def test_new_checkout_uses_dashboard_payment_methods_and_server_amount(flow):
    service, booking, event, _, _ = flow
    created = []

    def persist(payment):
        payment.id = str(uuid4())
        created.append(payment)
        return payment

    service.payments.create = MagicMock(side_effect=persist)
    service._locked.side_effect = lambda _: (booking, event, created[0] if created else None)
    service.gateway.create_checkout.return_value = {"id": "cs_dynamic", "url": "https://checkout.stripe.com/c/pay/dynamic"}
    result = service.create_checkout_session(booking.id, booking.user_id)
    params, key = service.gateway.create_checkout.call_args.args
    assert "payment_method_types" not in params
    assert "automatic_payment_methods" not in params
    assert params["mode"] == "payment"
    assert params["client_reference_id"] == booking.id
    assert params["line_items"][0]["price_data"]["unit_amount"] == 20000
    assert params["line_items"][0]["price_data"]["currency"] == "bob"
    assert key == f"checkout:{created[0].id}"
    assert created[0].payment_metadata["checkout_params_version"] == 2
    assert result.stripe_session_id == "cs_dynamic"


def test_checkout_with_reported_validation_error_upgrades_saved_params_without_rekeying(flow):
    service, booking, event, payment, _ = flow
    payment.stripe_checkout_session_id = None
    original = {"mode": "payment", "payment_method_types": ["card"], "client_reference_id": booking.id,
                "line_items": [{"quantity": 1, "price_data": {"currency": "bob", "unit_amount": 20000}}]}
    payment.payment_metadata = {
        "checkout_params": original,
        "last_checkout_error": {"category": "InvalidRequestError", "param": "payment_method_types", "request_id": "req_previous"},
    }
    service.gateway.create_checkout.return_value = {"id": "cs_upgraded", "url": "https://checkout.stripe.com/c/pay/upgraded"}
    service.create_checkout_session(booking.id, booking.user_id)
    params, key = service.gateway.create_checkout.call_args.args
    assert params == {name: value for name, value in original.items() if name != "payment_method_types"}
    assert original["payment_method_types"] == ["card"]
    assert key == f"checkout:{payment.id}"
    assert payment.payment_metadata["checkout_params_version"] == 2
    assert "last_checkout_error" not in payment.payment_metadata
    assert payment.amount == Decimal("200.00")
    assert payment.status == PaymentStatusEnum.PENDING
    assert booking.status == BookingStatusEnum.PENDING


@pytest.mark.parametrize("failure", [None, {"category": "APIConnectionError", "param": None}])
def test_legacy_attempt_with_unknown_remote_result_preserves_original_params(flow, failure):
    service, booking, event, payment, _ = flow
    payment.stripe_checkout_session_id = None
    params = {"mode": "payment", "payment_method_types": ["card"]}
    payment.payment_metadata = {"checkout_params": params, "last_checkout_error": failure}
    service.gateway.create_checkout.return_value = {"id": "cs_recovered", "url": "https://checkout.stripe.com/c/pay/recovered"}
    service.create_checkout_session(booking.id, booking.user_id)
    service.gateway.create_checkout.assert_called_once_with(params, f"checkout:{payment.id}")
    assert payment.payment_metadata["checkout_params"]["payment_method_types"] == ["card"]


def test_existing_session_is_retrieved_without_upgrading_legacy_params(flow):
    service, booking, event, payment, _ = flow
    params = {"mode": "payment", "payment_method_types": ["card"]}
    payment.payment_metadata = {"checkout_params": params, "last_checkout_error": {
        "category": "InvalidRequestError", "param": "payment_method_types",
    }}
    service.gateway.retrieve_checkout.return_value = {"id": "cs_test_known", "status": "open", "url": "https://checkout.stripe.com/c/pay/existing"}
    service.create_checkout_session(booking.id, booking.user_id)
    service.gateway.create_checkout.assert_not_called()
    service.gateway.retrieve_checkout.assert_called_once_with("cs_test_known")
    assert payment.payment_metadata["checkout_params"] == params


def test_dynamic_delayed_payment_does_not_issue_tickets_before_provider_confirmation(flow):
    service, booking, event, payment, remote = flow
    outcome = service._apply_session({**remote, "payment_status": "unpaid"}, booking, event, payment)
    assert outcome == "UNPAID"
    assert booking.status == BookingStatusEnum.PENDING
    assert payment.status == PaymentStatusEnum.PENDING
    assert event.reserved_slots == 0
    service.db.add.assert_not_called()


def test_refund_retry_uses_same_key_and_releases_seats_only_once(flow):
    service, booking, event, payment, remote = flow
    service._apply_session(remote, booking, event, payment)
    payment.payment_metadata = {"refund_requested": True, "refund_reason": "USER"}
    service.gateway.refund.side_effect = stripe.APIConnectionError("response lost")
    with pytest.raises(HTTPException) as error:
        service.process_refund(booking.id)
    assert error.value.status_code == 502
    assert booking.status == BookingStatusEnum.PAID
    service.gateway.refund.side_effect = None
    service.gateway.refund.return_value = {"id": "re_test", "status": "succeeded"}
    assert service.process_refund(booking.id) == "succeeded"
    assert service.process_refund(booking.id) == "succeeded"
    assert service.gateway.refund.call_count == 2
    assert service.gateway.refund.call_args.args[1] == f"refund:{payment.id}"
    assert booking.status == BookingStatusEnum.REFUNDED
    assert event.reserved_slots == 0
    assert event.status == ExperienceStatusEnum.OPEN


def test_pending_provider_refund_does_not_report_money_as_returned(flow):
    service, booking, event, payment, remote = flow
    service._apply_session(remote, booking, event, payment)
    payment.payment_metadata = {"refund_requested": True}
    service.gateway.refund.return_value = {"id": "re_pending", "status": "pending"}
    assert service.process_refund(booking.id) == "pending"
    assert booking.status == BookingStatusEnum.PAID
    assert event.reserved_slots == 2


def test_failed_checkout_saves_a_redacted_reason_without_changing_attempt_or_money(flow, caplog):
    service, booking, event, payment, remote = flow
    payment.stripe_checkout_session_id = None
    params = {"immutable": "stored parameters"}
    payment.payment_metadata = {"checkout_params": params}
    service.payments.get_by_booking_id = MagicMock(return_value=payment)
    secret = "sk_test_synthetic_private_secret"
    service.gateway.create_checkout.side_effect = stripe.InvalidRequestError(
        f"Amount below minimum; key={secret}", "amount", code="amount_too_small", headers={"request-id": "req_checkout_test"},
    )
    with patch.object(settings, "STRIPE_SECRET_KEY", secret), pytest.raises(HTTPException) as error:
        service.create_checkout_session(booking.id, booking.user_id)
    assert error.value.status_code == 422
    assert "mínimo" in error.value.detail
    assert payment.status == PaymentStatusEnum.PENDING
    assert booking.status == BookingStatusEnum.PENDING
    assert payment.payment_metadata["checkout_params"] == params
    assert payment.payment_metadata["last_checkout_error"]["code"] == "amount_too_small"
    assert "Stripe checkout failed" in caplog.text
    assert secret not in caplog.text
    assert secret not in str(payment.payment_metadata["last_checkout_error"])
    service.db.add.assert_not_called()

    service.gateway.create_checkout.side_effect = None
    service.gateway.create_checkout.return_value = {"id": "cs_retried", "url": "https://checkout.stripe.com/c/pay/retried"}
    service.create_checkout_session(booking.id, booking.user_id)
    assert "last_checkout_error" not in payment.payment_metadata
    assert service.gateway.create_checkout.call_args_list[0] == service.gateway.create_checkout.call_args_list[1]


def test_checkout_diagnostic_write_failure_does_not_hide_stripe_cause(flow, caplog):
    service, booking, event, payment, remote = flow
    service.gateway.retrieve_checkout.side_effect = stripe.AuthenticationError("Invalid API key")
    service.payments.get_by_booking_id = MagicMock(side_effect=RuntimeError("diagnostic write unavailable"))
    with pytest.raises(HTTPException) as error:
        service.create_checkout_session(booking.id, booking.user_id)
    assert error.value.status_code == 503
    assert "clave secreta" in error.value.detail
    assert "AuthenticationError" in caplog.text


@pytest.mark.parametrize("url", [None, "https://untrusted.example/pay?token=private-link"])
def test_invalid_checkout_response_also_has_a_safe_diagnostic(flow, caplog, url):
    service, booking, event, payment, remote = flow
    payment.stripe_checkout_session_id = None
    payment.payment_metadata = {"checkout_params": {"immutable": "parameters"}}
    service.gateway.create_checkout.return_value = {"id": "cs_invalid_response", "url": url}
    with pytest.raises(HTTPException) as error:
        service.create_checkout_session(booking.id, booking.user_id)
    assert error.value.status_code == 502
    assert "InvalidCheckoutResponse" in caplog.text
    assert "private-link" not in caplog.text
    assert payment.stripe_checkout_session_id is None
    assert booking.status == BookingStatusEnum.PENDING
