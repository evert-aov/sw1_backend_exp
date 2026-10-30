"""Adaptador Stripe con tiempos límite, claves por petición e idempotencia remota."""

import stripe
from fastapi import HTTPException
from app.core.config import settings


class StripeGateway:
    """Devuelve diccionarios recursivos; los recursos del SDK no son dict.

    No cambia la clave global del SDK ni recibe importes desde el navegador.
    """

    def _client(self):
        key = settings.STRIPE_SECRET_KEY
        if not key or "placeholder" in key:
            raise HTTPException(status_code=503, detail="Stripe no está configurado")
        return stripe.StripeClient(key, max_network_retries=1, http_client=stripe.RequestsClient(timeout=10))

    def create_checkout(self, params: dict, key: str):
        return self._client().v1.checkout.sessions.create(params, options={"idempotency_key": key}).to_dict()

    def retrieve_current_account(self):
        """Comprueba autenticación sin crear recursos ni solicitar cobros."""
        return self._client().v1.accounts.retrieve_current().to_dict()

    def retrieve_checkout(self, session_id: str):
        return self._client().v1.checkout.sessions.retrieve(session_id).to_dict()

    def expire_checkout(self, session_id: str):
        return self._client().v1.checkout.sessions.expire(session_id).to_dict()

    def refund(self, intent_id: str, key: str):
        return self._client().v1.refunds.create({"payment_intent": intent_id}, options={"idempotency_key": key}).to_dict()

    def retrieve_refund(self, refund_id: str):
        return self._client().v1.refunds.retrieve(refund_id).to_dict()

    def verify_event(self, payload: bytes, signature: str):
        secret = settings.STRIPE_WEBHOOK_SECRET
        if not secret or "placeholder" in secret:
            raise HTTPException(status_code=503, detail="El webhook Stripe no está configurado")
        try:
            return stripe.Webhook.construct_event(payload, signature, secret).to_dict()
        except (ValueError, stripe.SignatureVerificationError) as error:
            raise HTTPException(status_code=400, detail="Firma o cuerpo de webhook inválido") from error
