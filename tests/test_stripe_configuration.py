"""El diagnóstico de Stripe nunca imprime credenciales ni mensajes sensibles del SDK."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import stripe
from scripts import check_stripe


@pytest.mark.parametrize("failure", ["authentication", "connection"])
def test_stripe_diagnostic_does_not_expose_secret_in_provider_failure(failure):
    secret = "sk_test_only_a_synthetic_secret"
    config = SimpleNamespace(STRIPE_SECRET_KEY=secret, STRIPE_PUBLISHABLE_KEY="pk_test_synthetic", STRIPE_WEBHOOK_SECRET="")
    error = (stripe.AuthenticationError(f"Invalid API Key provided: {secret}") if failure == "authentication"
             else stripe.APIConnectionError(f"Connection failed with token {secret}"))
    output = StringIO()
    with patch.object(check_stripe, "settings", config), patch.object(check_stripe.StripeGateway, "retrieve_current_account", side_effect=error), redirect_stdout(output), redirect_stderr(output):
        assert check_stripe.main() == 2
    assert secret not in output.getvalue()
    assert "pk_test_synthetic" not in output.getvalue()


def test_successful_stripe_diagnostic_does_not_print_account_data():
    config = SimpleNamespace(STRIPE_SECRET_KEY="sk_test_synthetic", STRIPE_PUBLISHABLE_KEY="pk_test_synthetic", STRIPE_WEBHOOK_SECRET="whsec_synthetic")
    output = StringIO()
    with patch.object(check_stripe, "settings", config), patch.object(check_stripe.StripeGateway, "retrieve_current_account", return_value={"business_profile": {"name": "private-account-name"}}) as retrieve, redirect_stdout(output):
        assert check_stripe.main() == 0
    retrieve.assert_called_once_with()
    assert "private-account-name" not in output.getvalue()
    assert config.STRIPE_SECRET_KEY not in output.getvalue()
    assert config.STRIPE_WEBHOOK_SECRET not in output.getvalue()
