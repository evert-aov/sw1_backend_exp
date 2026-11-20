"""
Envío de notificaciones push con Firebase Cloud Messaging, API HTTP v1 (HU-18).

Requiere la variable de entorno `FIREBASE_CREDENTIALS_PATH` con la ruta al JSON de la cuenta de
servicio del proyecto Firebase. Ese archivo es un secreto: nunca se versiona. Sin esa variable el
servicio queda desactivado y las alertas siguen llegando por WebSocket.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"

# Canal de notificación Android creado por la app móvil para las alertas del MC
ANDROID_CHANNEL_ID = "mc_alerts"

# Errores de FCM que indican que el token ya no sirve y debe eliminarse
INVALID_TOKEN_ERRORS = frozenset({"UNREGISTERED", "SENDER_ID_MISMATCH"})


@dataclass(frozen=True)
class PushMessage:
    """Notificación dirigida a un dispositivo."""

    token: str
    title: str
    body: str
    data: dict[str, str] = field(default_factory=dict)


class PushNotificationService:
    """Cliente mínimo de Firebase Cloud Messaging con credenciales de cuenta de servicio."""

    def __init__(
        self,
        credentials_path: str | None = None,
        post: Callable[..., httpx.Response] | None = None,
        token_provider: Callable[[], tuple[str, str]] | None = None,
    ) -> None:
        """
        Inicializa el servicio.

        Args:
            credentials_path (str | None): Ruta al JSON de la cuenta de servicio; por defecto
                `FIREBASE_CREDENTIALS_PATH`.
            post (Callable[..., httpx.Response] | None): Función HTTP POST inyectable para pruebas.
            token_provider (Callable[[], tuple[str, str]] | None): Proveedor de (token OAuth, project_id)
                inyectable para pruebas.
        """
        if credentials_path is not None:
            resolved_path = credentials_path
        else:
            from app.core.config import BACKEND_ROOT, settings

            raw_path = os.getenv("FIREBASE_CREDENTIALS_PATH") or settings.FIREBASE_CREDENTIALS_PATH
            if raw_path and not Path(raw_path).is_absolute():
                resolved_path = str((BACKEND_ROOT / raw_path).resolve())
            else:
                resolved_path = raw_path
        self._path = resolved_path
        self._post = post or httpx.post
        self._token_provider = token_provider
        self._credentials: Any = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        """
        Indica si hay credenciales de Firebase disponibles.

        Returns:
            bool: True si el envío push está configurado.
        """
        return self._token_provider is not None or (bool(self._path) and Path(self._path).is_file())

    def _access_token(self) -> tuple[str, str]:
        """
        Obtiene un token OAuth vigente y el ID del proyecto Firebase.

        Returns:
            tuple[str, str]: Token de acceso y `project_id`.
        """
        if self._token_provider is not None:
            return self._token_provider()
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        with self._lock:
            if self._credentials is None:
                self._credentials = service_account.Credentials.from_service_account_file(
                    self._path, scopes=[FCM_SCOPE]
                )
            if not self._credentials.valid:
                self._credentials.refresh(Request())
            return str(self._credentials.token), str(self._credentials.project_id)

    def send(self, messages: list[PushMessage]) -> list[str]:
        """
        Envía las notificaciones y devuelve los tokens que Firebase rechazó como inválidos.

        Los errores de red o de configuración se registran sin propagarse: una falla de push nunca
        debe interrumpir la telemetría ni la alerta por WebSocket.

        Args:
            messages (list[PushMessage]): Notificaciones a enviar.

        Returns:
            list[str]: Tokens que deben eliminarse.
        """
        if not messages or not self.enabled:
            return []
        try:
            access_token, project_id = self._access_token()
        except Exception as exc:
            logger.warning("Firebase no disponible, no se enviaron notificaciones push: %s", exc)
            return []

        invalid: list[str] = []
        url = FCM_SEND_URL.format(project_id=project_id)
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        for message in messages:
            try:
                response = self._post(url, json=self._payload(message), headers=headers, timeout=10)
            except httpx.HTTPError as exc:
                logger.warning("Fallo de red al enviar push: %s", exc)
                continue
            if response.status_code == 200:
                continue
            if self._is_invalid_token(response):
                invalid.append(message.token)
            else:
                logger.warning(
                    "Firebase rechazó la notificación (%s): %s",
                    response.status_code,
                    response.text[:200],
                )
        return invalid

    @staticmethod
    def _payload(message: PushMessage) -> dict[str, Any]:
        """
        Construye el cuerpo de la API HTTP v1 de FCM.

        Args:
            message (PushMessage): Notificación a enviar.

        Returns:
            dict[str, Any]: Cuerpo JSON con prioridad alta y canal Android de alertas.
        """
        return {
            "message": {
                "token": message.token,
                "notification": {"title": message.title, "body": message.body},
                "data": message.data,
                "android": {
                    "priority": "HIGH",
                    "notification": {"channel_id": ANDROID_CHANNEL_ID},
                },
            }
        }

    @staticmethod
    def _is_invalid_token(response: httpx.Response) -> bool:
        """
        Indica si la respuesta de FCM corresponde a un token inválido o desregistrado.

        Args:
            response (httpx.Response): Respuesta de error de FCM.

        Returns:
            bool: True si el token debe eliminarse.
        """
        if response.status_code == 404:
            return True
        try:
            details = response.json().get("error", {}).get("details", [])
        except ValueError:
            return False
        return any(
            detail.get("errorCode") in INVALID_TOKEN_ERRORS
            for detail in details
            if isinstance(detail, dict)
        )
