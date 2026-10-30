"""Diagnóstico de Stripe con mensajes públicos separados de credenciales y datos privados."""

from dataclasses import dataclass
import re
from urllib.parse import quote
import stripe
from app.core.config import settings


def redacted_message(value) -> str:
    """Usa solo el mensaje, nunca cuerpos/headers completos, y elimina secretos conocidos."""
    message = " ".join(str(value or "Sin descripción del proveedor").split())
    secrets = [settings.STRIPE_SECRET_KEY, settings.STRIPE_PUBLISHABLE_KEY,
               settings.STRIPE_WEBHOOK_SECRET, settings.JWT_SECRET, settings.DB_PASS]
    if settings.DATABASE_URL:
        secrets.append(settings.DATABASE_URL)
    for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
        message = message.replace(secret, "[REDACTED]").replace(quote(secret, safe=""), "[REDACTED]")
    message = re.sub(r"\b(?:sk|rk|pk)_(?:test|live)_[A-Za-z0-9]+|\bwhsec_[A-Za-z0-9]+", "[REDACTED]", message)
    message = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", message)
    message = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", message)
    return message[:600]


def identifier(value, pattern: str) -> str | None:
    """Solo permite IDs/códigos acotados, evitando texto libre y claves en esos campos."""
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        return None
    if re.search(r"(?:sk|rk|pk)_(?:test|live)_|whsec_", value):
        return None
    return value


@dataclass(frozen=True)
class StripeFailure:
    status: int
    detail: str
    category: str
    code: str | None
    param: str | None
    request_id: str | None
    message: str

    def diagnostic(self) -> dict:
        """Registro acotado para operador y pago; no incluye la petición Stripe."""
        return {"category": self.category, "code": self.code, "param": self.param,
                "request_id": self.request_id, "message": self.message}


def describe_stripe_failure(error: stripe.StripeError) -> StripeFailure:
    """Traduce causas comprobadas por el SDK sin atribuir una causa no observada."""
    code = identifier(getattr(error, "code", None), r"[a-z0-9_]{1,80}")
    param = identifier(getattr(error, "param", None), r"[A-Za-z0-9_\[\].]{1,120}")
    request_id = identifier(getattr(error, "request_id", None), r"req_[A-Za-z0-9_]{1,100}")
    status = 502
    if isinstance(error, stripe.AuthenticationError):
        status, detail = 503, "Stripe rechazó la clave secreta del backend. Revisa STRIPE_SECRET_KEY y reinicia la API."
    elif isinstance(error, stripe.PermissionError):
        status, detail = 503, "La clave de Stripe no tiene permisos para iniciar este pago."
    elif isinstance(error, stripe.APIConnectionError):
        detail = "El backend no pudo conectarse con Stripe. Revisa su conexión y reintenta la misma reserva."
    elif isinstance(error, stripe.RateLimitError):
        status, detail = 503, "Stripe limitó temporalmente las solicitudes. Espera antes de reintentar la misma reserva."
    elif isinstance(error, stripe.IdempotencyError):
        status, detail = 409, "Stripe detectó un conflicto con este intento de pago. Actualiza su estado antes de reintentar."
    elif isinstance(error, stripe.InvalidRequestError):
        status = 422
        if code == "amount_too_small":
            detail = "El importe de esta reserva no alcanza el mínimo que Stripe admite para la moneda de cobro."
        elif code == "amount_too_large":
            detail = "El importe de esta reserva supera el máximo admitido por Stripe."
        elif code in {"currency_not_supported", "currency_unsupported"} or (param and "currency" in param):
            status, detail = 503, "Stripe rechazó la moneda configurada para este pago. Revisa la configuración de la cuenta."
        elif param in {"success_url", "cancel_url", "return_url"}:
            status, detail = 503, "Stripe rechazó la URL de retorno. Revisa FRONTEND_URL en el backend."
        else:
            detail = "Stripe rechazó los datos del checkout. Revisa el diagnóstico del backend."
    elif isinstance(error, stripe.CardError):
        status, detail = 402, "Stripe rechazó el medio de pago. Usa otro medio o consulta al emisor."
    else:
        detail = "Stripe no pudo completar la solicitud. Actualiza el estado antes de reintentar."
    reference = request_id or code
    if reference:
        detail += f" Referencia: {reference}."
    return StripeFailure(status, detail, type(error).__name__, code, param, request_id,
                         redacted_message(getattr(error, "user_message", None)))
