"""Regresión del 502 genérico: causas del SDK y diagnóstico sin credenciales."""

from unittest.mock import patch
import pytest
import stripe
from app.core.config import settings
from app.booking.service.stripe_errors import describe_stripe_failure


@pytest.mark.parametrize("error,status,fragment", [
    (stripe.AuthenticationError("Invalid API key"), 503, "clave secreta"),
    (stripe.PermissionError("Permission denied"), 503, "permisos"),
    (stripe.APIConnectionError("Could not connect"), 502, "conectarse"),
    (stripe.RateLimitError("Rate limit"), 503, "temporalmente"),
    (stripe.IdempotencyError("Parameters changed"), 409, "conflicto"),
    (stripe.InvalidRequestError("Below minimum", "amount", code="amount_too_small"), 422, "mínimo"),
    (stripe.InvalidRequestError("Above maximum", "amount", code="amount_too_large"), 422, "máximo"),
    (stripe.InvalidRequestError("Currency not available", "line_items[0][price_data][currency]"), 503, "moneda"),
    (stripe.InvalidRequestError("Invalid URL", "success_url"), 503, "FRONTEND_URL"),
    (stripe.InvalidRequestError("Business setup incomplete", None), 422, "diagnóstico"),
    (stripe.APIError("Provider unavailable"), 502, "estado"),
])
def test_stripe_errors_are_classified_without_guessing_the_cause(error, status, fragment):
    failure = describe_stripe_failure(error)
    assert failure.status == status
    assert fragment in failure.detail
    assert failure.category == type(error).__name__


def test_provider_diagnostic_redacts_credentials_and_preserves_request_reference():
    secret = "sk_test_synthetic_PRIVATE_TOKEN"
    webhook = "whsec_synthetic_PRIVATE_TOKEN"
    message = f"Invalid credentials {secret}; webhook {webhook}; Bearer abc.def.ghi; owner person@example.com"
    error = stripe.InvalidRequestError(message, "success_url", code="url_invalid", headers={"request-id": "req_synthetic"})
    with patch.object(settings, "STRIPE_SECRET_KEY", secret), patch.object(settings, "STRIPE_WEBHOOK_SECRET", webhook):
        failure = describe_stripe_failure(error)
    diagnostic = str(failure.diagnostic())
    assert secret not in diagnostic
    assert webhook not in diagnostic
    assert "abc.def.ghi" not in diagnostic
    assert "person@example.com" not in diagnostic
    assert failure.request_id == "req_synthetic"
    assert "req_synthetic" in failure.detail
    assert failure.param == "success_url"


def test_metadata_fields_cannot_be_used_to_print_keys_or_multiline_text():
    error = stripe.InvalidRequestError("Invalid field", "whsec_fake_key", code="sk_test_fake_key",
                                       headers={"request-id": "req_fake\nprivate"})
    failure = describe_stripe_failure(error)
    assert failure.code is None
    assert failure.param is None
    assert failure.request_id is None
