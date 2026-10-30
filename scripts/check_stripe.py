"""Comprueba configuración y autenticación Stripe mediante una consulta de solo lectura."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import stripe
from fastapi import HTTPException
from app.core.config import settings
from app.booking.service.stripe_gateway import StripeGateway


def main() -> int:
    """No imprime claves, cuenta, saldos ni mensajes del proveedor que contengan secretos."""
    key = settings.STRIPE_SECRET_KEY
    if not key or "placeholder" in key:
        print("Falta STRIPE_SECRET_KEY en el .env del backend.", file=sys.stderr)
        return 1
    if key.startswith("sk_test_"):
        print("Clave secreta de prueba configurada.")
    elif key.startswith("sk_live_"):
        print("Clave secreta de producción configurada; esta comprobación solo consulta la cuenta.")
    else:
        print("Revisa el formato de STRIPE_SECRET_KEY.", file=sys.stderr)
        return 1
    public = settings.STRIPE_PUBLISHABLE_KEY
    if public:
        matching_mode = (key.startswith("sk_test_") and public.startswith("pk_test_")) or (
            key.startswith("sk_live_") and public.startswith("pk_live_"))
        if not matching_mode:
            print("Las claves pública/secreta no tienen el mismo modo.", file=sys.stderr)
            return 1
        print("Clave publicable del mismo modo configurada; Hosted Checkout no la requiere.")
    webhook = settings.STRIPE_WEBHOOK_SECRET
    webhook_present = bool(webhook and webhook.startswith("whsec_") and "placeholder" not in webhook)
    print("Secreto de webhook:", "presente (requiere comprobar un evento firmado)" if webhook_present else "pendiente")
    try:
        StripeGateway().retrieve_current_account()
    except stripe.AuthenticationError:
        print("Stripe rechazó la clave. Revisa si sigue activa en tu cuenta.", file=sys.stderr)
        return 2
    except stripe.APIConnectionError:
        print("No se pudo conectar con Stripe. La validez de la clave no está comprobada.", file=sys.stderr)
        return 2
    except stripe.StripeError as error:
        print(f"Stripe no completó la comprobación ({type(error).__name__}).", file=sys.stderr)
        return 2
    except HTTPException:
        print("Stripe no está configurado correctamente.", file=sys.stderr)
        return 1
    print("Autenticación Stripe comprobada. No se crearon recursos ni cobros.")
    return 0 if webhook_present else 1


if __name__ == "__main__":
    raise SystemExit(main())
