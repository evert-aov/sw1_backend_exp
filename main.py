from __future__ import annotations

import os
import socket

_prebound_socket: socket.socket | None = None
if __name__ == "__main__":
    _port = int(os.getenv("PORT", "3000"))
    _host = os.getenv("HOST", "0.0.0.0")
    _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        _sock.bind((_host, _port))
        _sock.listen(128)
        _prebound_socket = _sock
    except OSError:
        _sock.close()
        _prebound_socket = None

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, ConfigDict, Field
from app.auth.control import auth_router, users_router
from app.booking.control import booking_router, payment_router, subscription_router
from app.core.config import settings
from app.core.database import init_db
from app.core.system_controller import system_router
from app.experience.control import category_router, experience_router, venue_router
from app.live.control import live_router, report_router
from app.matching.control import demand_router, matching_router


class HealthCheckResponseDTO(BaseModel):
    """
    Contrato de respuesta para el endpoint de estado de salud del sistema (`GET /`).
    """

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(default="online", description="Estado operativo de la API")
    project: str = Field(..., description="Nombre del proyecto")
    version: str = Field(..., description="Versión de la API")
    python_target: str = Field(default="3.14.6", description="Estándar de tipado Python objetivo")
    sprint_1_use_cases: list[str] = Field(
        default_factory=list,
        description="Casos de uso del Sprint 1 verificados y activos",
    )
    swagger_ui: str = Field(default="/docs", description="Ruta hacia la documentación interactiva Swagger UI")
    redoc: str = Field(default="/redoc", description="Ruta hacia la documentación ReDoc")
    openapi_schema: str = Field(default="/openapi.json", description="Ruta hacia el esquema OpenAPI JSON")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Administrador de ciclo de vida asíncrono de FastAPI.
    Inicializa el esquema de base de datos y los datos semilla de demostración al arrancar el servidor.
    """
    import threading

    def _safe_init() -> None:
        try:
            init_db()
        except Exception as e:
            print(f"[Database Warning] No se pudo sincronizar automáticamente: {e}")

    threading.Thread(target=_safe_init, daemon=True).start()
    yield


# Definición de etiquetas descriptivas para Swagger UI agrupadas por módulos y Casos de Uso
tags_metadata: list[dict[str, str]] = [
    {
        "name": "Auth Controller (CU-01, CU-02)",
        "description": (
            "CU-01: Registrar Cuenta y CU-02: Autenticar Usuario (Login, Logout con revocación "
            "de token y Refresh con JWT)."
        ),
    },
    {
        "name": "Users Controller (CU-03)",
        "description": (
            "CU-03: Gestionar Perfil de Usuario y Preferencias (datos personales, avatar, "
            "biografía y etiquetas de intereses temáticos)."
        ),
    },
    {
        "name": "Experience Controller (CU-04, CU-05)",
        "description": (
            "CU-04: Publicar Experiencia (gestión de eventos, aforos, quórum y desglose de comisiones) "
            "y CU-05: Explorar y Filtrar Experiencias (catálogo web y móvil por geolocalización Haversine)."
        ),
    },
    {
        "name": "Categories Controller",
        "description": "Administración de categorías temáticas de experiencias (Gastronomía, Arte, Música, etc.).",
    },
    {
        "name": "Venues Controller",
        "description": "Administración y registro de espacios físicos y locales comerciales geolocalizados.",
    },
    {
        "name": "Booking Controller (CU-06)",
        "description": "Gestión de reservas de cupos, comisiones escalonadas de plataforma y validación de tickets QR.",
    },
    {
        "name": "Payment & Stripe Controller",
        "description": "Integración con Stripe Checkout Sessions y recepción de Webhooks para confirmación de pagos.",
    },
    {
        "name": "SaaS Subscriptions Controller (CU-14)",
        "description": "Suscripciones recurrentes a planes Pro para anfitriones y locales con Stripe Billing.",
    },
    {
        "name": "Matching Controller (CU-07)",
        "description": "Algoritmo de agrupación dinámica por intereses para asegurar el quórum mínimo antes de la fecha límite.",
    },
    {
        "name": "Demand Insights Controller (CU-08)",
        "description": "Prospección de demanda insatisfecha por zonas urbanas y sugerencias inteligentes para creación de eventos.",
    },
    {
        "name": "Live & WebSocket Controller (CU-09, CU-10, CU-11, CU-12)",
        "description": "Canal WebSocket para muestreo efímero de video (GDPR en RAM) y telemetría de engagement en vivo con alertas MC y DJ Virtual.",
    },
    {
        "name": "Post-Event Analytics Report Controller (CU-13)",
        "description": "Consulta de curvas de atención y entusiasmo minuto a minuto y exportación de reportes en PDF.",
    },
    {
        "name": "System & Database Administration",
        "description": "Herramientas de mantenimiento para vaciar la base de datos en cascada y poblar datos semilla (Seeder).",
    },
]

# Inicialización de la aplicación FastAPI con parámetros personalizados para Swagger UI
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="""
## EXPERIENCIA — API RESTful & WebSockets (Python 3.14.6 + FastAPI)

Ecosistema tecnológico para conectar usuarios con experiencias presenciales, virtuales e híbridas de cupo limitado, optimizando la interacción de la audiencia en tiempo real mediante Visión Artificial e IA.

### Casos de Uso del Sprint 1 Operativos:
- **CU-01:** Registrar Cuenta (`POST /api/auth/register`)
- **CU-02:** Autenticar Usuario — Login / Logout / Refresh con JWT (`POST /api/auth/login`, `POST /api/auth/logout`, `POST /api/auth/refresh`)
- **CU-03:** Gestionar Perfil de Usuario y Preferencias (`GET /api/users/me`, `PUT /api/users/me`, `PATCH /api/users/me/preferences`)
- **CU-04:** Publicar Experiencia — Gestión de eventos, aforos y precios (`POST /api/experiences`, `PUT /api/experiences/{id}`, `PATCH /api/experiences/{id}/cancel`, `GET /api/experiences/me/hosted`)
- **CU-05:** Explorar y Filtrar Experiencias — Catálogo web y móvil por geolocalización (`GET /api/experiences/catalog`)

Para consumir endpoints protegidos:
1. Inicia sesión en `/api/auth/login` (contraseña semilla: `Password123!`) para obtener tu **JWT token**.
2. Haz clic en el botón **Authorize** en la parte superior derecha.
3. Ingresa tu token JWT.
    """,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "docExpansion": "list",
        "defaultModelsExpandDepth": 1,
    },
    lifespan=lifespan,
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registro de routers por paquetes
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(users_router, prefix=settings.API_V1_STR)

app.include_router(experience_router, prefix=settings.API_V1_STR)
app.include_router(category_router, prefix=settings.API_V1_STR)
app.include_router(venue_router, prefix=settings.API_V1_STR)

app.include_router(booking_router, prefix=settings.API_V1_STR)
app.include_router(payment_router, prefix=settings.API_V1_STR)
app.include_router(subscription_router, prefix=settings.API_V1_STR)

app.include_router(matching_router, prefix=settings.API_V1_STR)
app.include_router(demand_router, prefix=settings.API_V1_STR)

app.include_router(live_router, prefix=settings.API_V1_STR)
app.include_router(report_router, prefix=settings.API_V1_STR)

app.include_router(system_router, prefix=settings.API_V1_STR)


def custom_openapi() -> dict[str, Any]:
    """
    Personaliza el esquema OpenAPI 3.1 inyectando los esquemas de seguridad HTTP Bearer JWT
    para facilitar la autenticación interactiva desde Swagger UI.

    Returns:
        dict[str, Any]: Diccionario con la especificación OpenAPI generada.
    """
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=tags_metadata,
    )

    openapi_schema["components"] = openapi_schema.get("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Pega tu access_token JWT aquí (funciona con o sin 'Bearer').",
        },
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Pega tu access_token JWT aquí (funciona con o sin 'Bearer').",
        },
    }

    openapi_schema["security"] = [{"HTTPBearer": []}, {"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]


@app.get(
    "/",
    response_model=HealthCheckResponseDTO,
    status_code=status.HTTP_200_OK,
    tags=["Health Check"],
    summary="Verificar estado operativo de la API y enlaces de documentación",
    description="Devuelve el estado de salud del servidor, la versión de Python/FastAPI y los Casos de Uso activos del Sprint 1.",
)
def health_check() -> HealthCheckResponseDTO:
    """
    Verifica el estado operativo de la aplicación EXPERIENCIA API y expone las rutas de documentación.

    Returns:
        HealthCheckResponseDTO: Información del estado del servicio y casos de uso activos.
    """
    return HealthCheckResponseDTO(
        status="online",
        project=settings.PROJECT_NAME,
        version=settings.VERSION,
        python_target=settings.PYTHON_TARGET_VERSION,
        sprint_1_use_cases=[
            "CU-01: Registrar Cuenta",
            "CU-02: Autenticar Usuario (Login / Logout con JWT)",
            "CU-03: Gestionar Perfil de Usuario y Preferencias",
            "CU-04: Publicar Experiencia (Gestión de eventos, aforos y precios)",
            "CU-05: Explorar y Filtrar Experiencias (Catálogo web y móvil por geolocalización)",
        ],
        swagger_ui="/docs",
        redoc="/redoc",
        openapi_schema="/openapi.json",
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "3000"))
    host = os.getenv("HOST", "0.0.0.0")
    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)
    if _prebound_socket is not None:
        server.run(sockets=[_prebound_socket])
    else:
        server.run()

