"""Pruebas HTTP de rechazos tempranos; no abren conexión PostgreSQL."""

import asyncio
import unittest
import httpx
from unittest.mock import MagicMock, patch
from uuid import uuid4
from main import app
from app.core.database import get_db
from app.core.security import get_current_active_user
from app.auth.entity.user import User


class HttpSecurityTests(unittest.IsolatedAsyncioTestCase):
    """Comprueba rutas reales por ASGI sin iniciar el lifespan de infraestructura."""

    async def asyncSetUp(self):
        """Mantiene el bucle activo para dependencias síncronas en este entorno aislado."""

        async def pulse():
            """Despierta el bucle cuando el sandbox limita señalización entre hilos."""
            while True:
                await asyncio.sleep(0.01)

        self.pulse = asyncio.create_task(pulse())
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def asyncTearDown(self):
        """Cierra transporte y tarea auxiliar de la prueba."""
        await self.client.aclose()
        self.pulse.cancel()
        await asyncio.gather(self.pulse, return_exceptions=True)

    async def test_maintenance_rejects_anonymous_requests(self):
        """Ninguna operación administrativa se ejecuta sin JWT autorizado."""
        for path in ("reset-db", "seed", "reset-and-seed"):
            response = await asyncio.wait_for(
                self.client.post(f"/api/system/{path}"), 5
            )
            self.assertEqual(response.status_code, 401)

    async def test_admin_registration_is_rejected_over_http(self):
        """El rechazo público ocurre antes de consultar/escribir la base."""
        response = await asyncio.wait_for(
            self.client.post(
                "/api/auth/register",
                json={
                    "first_name": "Test",
                    "email": "test@example.com",
                    "password": "password123",
                    "role": "ADMIN",
                },
            ),
            5,
        )
        self.assertEqual(response.status_code, 400)

    async def test_commission_quote_uses_canonical_policy(self):
        """El formulario puede consultar la política sin inventar su propia comisión."""
        response = await asyncio.wait_for(
            self.client.get(
                "/api/experiences/commission-quote", params={"price": "100"}
            ),
            5,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["commission_rate"], 0.08)

    async def test_ticket_and_checkout_require_authentication(self):
        """Conocer un código o ID no habilita ver entradas ni iniciar checkout."""
        response = await asyncio.wait_for(
            self.client.get("/api/bookings/tickets/verify/example"), 5
        )
        self.assertEqual(response.status_code, 401)

    async def test_demand_and_notifications_require_authentication(self):
        for path in (
            "/api/demand/insights",
            "/api/demand/suggestions",
            "/api/notifications",
            "/api/matching/group/example",
        ):
            response = await asyncio.wait_for(self.client.get(path), 5)
            self.assertEqual(response.status_code, 401)
        response = await asyncio.wait_for(
            self.client.post("/api/payments/checkout/example"), 5
        )
        self.assertEqual(response.status_code, 401)

    async def test_routes_enforce_assigned_roles_even_with_an_authenticated_session(
        self,
    ):
        db = MagicMock()
        user = User(
            id=str(uuid4()), first_name="Test", email="test@example.com", is_active=True
        )
        previous = dict(app.dependency_overrides)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_active_user] = lambda: user
        try:
            cases = [
                (
                    ["HOST"],
                    [
                        ("GET", "/api/bookings/my-tickets"),
                        ("POST", "/api/payments/checkout/example"),
                        ("GET", "/api/matching/group/example"),
                        ("GET", "/api/users"),
                        ("GET", "/api/users/00000000-0000-0000-0000-000000000001"),
                        ("GET", "/api/admin/overview"),
                    ],
                ),
                (
                    ["ATTENDEE"],
                    [
                        ("GET", "/api/experiences/me/hosted"),
                        ("GET", "/api/venues/me/owned"),
                        ("POST", "/api/bookings/tickets/check-in"),
                        ("GET", "/api/admin/overview"),
                    ],
                ),
                (
                    ["ADMIN"],
                    [
                        ("GET", "/api/experiences/me/hosted"),
                        ("GET", "/api/bookings/my-tickets"),
                        ("GET", "/api/venues/me/owned"),
                    ],
                ),
                (
                    [],
                    [
                        ("GET", "/api/bookings/my-tickets"),
                        ("GET", "/api/experiences/me/hosted"),
                    ],
                ),
            ]
            for roles, endpoints in cases:
                with patch(
                    "app.auth.repository.user_repository.UserRepository.get_user_roles",
                    return_value=roles,
                ):
                    for method, path in endpoints:
                        response = await asyncio.wait_for(
                            self.client.request(method, path, json={"code": "sample"}),
                            5,
                        )
                        self.assertEqual(
                            response.status_code, 403, (roles, path, response.text)
                        )
            db.commit.assert_not_called()
            with (
                patch(
                    "app.auth.repository.user_repository.UserRepository.get_user_roles",
                    return_value=["HOST", "ATTENDEE"],
                ),
                patch(
                    "app.experience.service.experience_service.ExperienceService.get_my_hosted_experiences",
                    return_value=[],
                ),
                patch(
                    "app.experience.service.venue_service.VenueService.get_my_venues",
                    return_value=[],
                ),
                patch(
                    "app.booking.service.booking_service.BookingService.get_user_bookings",
                    return_value=[],
                ),
            ):
                for path in [
                    "/api/bookings/my-tickets",
                    "/api/experiences/me/hosted",
                    "/api/venues/me/owned",
                ]:
                    response = await asyncio.wait_for(self.client.get(path), 5)
                    self.assertEqual(response.status_code, 200, response.text)
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
