from __future__ import annotations

import os
import socket
from dotenv import load_dotenv

load_dotenv()

_prebound_socket: socket.socket | None = None
if __name__ == "__main__":
    _port = int(os.getenv("PORT", "8000"))
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

from collections.abc import AsyncGenerator  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from typing import Any  # noqa: E402

# Estas importaciones quedan debajo del prebind opcional; las excepciones E402 se limitan a estas líneas.
from app.auth.control import auth_router, users_router  # noqa: E402
from app.booking.control import booking_router, payment_router, subscription_router  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import engine, init_db  # noqa: E402
from app.core.diagnostics import (  # noqa: E402
    REQUEST_ID_HEADER,
    CauseStatus,
    ErrorCode,
    RequestIdMiddleware,
    error_payload,
    install_diagnostic_handlers,
    log_diagnostic_event,
    log_operational_event,
)
from app.core.system_controller import system_router  # noqa: E402
from app.experience.control import category_router, experience_router, venue_router  # noqa: E402
from app.live.control import age_distribution_router, live_router, report_router  # noqa: E402
from app.matching.control import demand_router, matching_router  # noqa: E402
from app.notifications.controller import notification_router  # noqa: E402
from fastapi import FastAPI, Request, status  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.openapi.utils import get_openapi  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402


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
    swagger_ui: str = Field(
        default="/docs", description="Ruta hacia la documentación interactiva Swagger UI"
    )
    redoc: str = Field(default="/redoc", description="Ruta hacia la documentación ReDoc")
    openapi_schema: str = Field(
        default="/openapi.json", description="Ruta hacia el esquema OpenAPI JSON"
    )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Administrador de ciclo de vida asíncrono de FastAPI.
    Verifica PostgreSQL antes de aceptar tráfico y libera el pool al cerrar.
    """
    import asyncio

    from app.core.database import engine

    log_operational_event(
        event="startup.check_started",
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        evidence={"dependency": "postgresql", "phase": "startup"},
    )
    try:
        await asyncio.to_thread(init_db)
    except Exception as exc:
        log_diagnostic_event(
            event="startup.check_failed",
            service=settings.PROJECT_NAME,
            version=settings.VERSION,
            request_id=None,
            error_code=ErrorCode.INTERNAL_ERROR,
            cause_status=CauseStatus.HYPOTHESIS,
            evidence={
                "dependency": "postgresql",
                "phase": "startup",
                "exception_type": type(exc).__name__,
            },
        )
        raise
    log_operational_event(
        event="startup.ready",
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        evidence={"dependency": "postgresql", "phase": "startup"},
    )
    try:
        yield
    finally:
        engine.dispose()


# Definición de etiquetas descriptivas para Swagger UI agrupadas por módulos y Casos de Uso
tags_metadata: list[dict[str, str]] = [
    {
        "name": "Auth Controller (CU-01)",
        "description": (
            "CU-01: Registrar Cuenta y CU-01: Autenticar Usuario (Login, Logout con revocación "
            "de token y Refresh con JWT)."
        ),
    },
    {
        "name": "Users Controller (CU-02)",
        "description": (
            "CU-02: Gestionar Perfil de Usuario y Preferencias (datos personales, avatar, "
            "biografía y etiquetas de intereses temáticos)."
        ),
    },
    {
        "name": "Experience Controller (CU-03, CU-04)",
        "description": (
            "CU-03: Publicar Experiencia (gestión de eventos, aforos, quórum y desglose de comisiones) "
            "y CU-04: Explorar y Filtrar Experiencias (catálogo web y móvil por geolocalización Haversine)."
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
        "name": "Booking Controller (CU-05)",
        "description": "Gestión de reservas de cupos, comisiones escalonadas de plataforma y validación de tickets QR.",
    },
    {
        "name": "Payment & Stripe Controller",
        "description": "Integración con Stripe Checkout Sessions y recepción de Webhooks para confirmación de pagos.",
    },
    {
        "name": "SaaS Subscriptions Controller (CU-13)",
        "description": "Suscripciones recurrentes a planes Pro para anfitriones y locales con Stripe Billing.",
    },
    {
        "name": "Matching Controller (CU-06)",
        "description": "Algoritmo de agrupación dinámica por intereses para asegurar el quórum mínimo antes de la fecha límite.",
    },
    {
        "name": "Demand Insights Controller (CU-07)",
        "description": "Prospección de demanda insatisfecha por zonas urbanas y sugerencias inteligentes para creación de eventos.",
    },
    {
        "name": "Live & WebSocket Controller (CU-08, CU-09, CU-10, CU-11)",
        "description": "Canal WebSocket para muestreo efímero de video (GDPR en RAM) y telemetría de engagement en vivo con alertas MC y DJ Virtual.",
    },
    {
        "name": "Post-Event Analytics Report Controller (CU-12)",
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
- **CU-01:** Autenticación — Registro (`POST /api/auth/register`), Login / Logout / Refresh. Autenticar Usuario — Login / Logout / Refresh con JWT (`POST /api/auth/login`, `POST /api/auth/logout`, `POST /api/auth/refresh`)
- **CU-02:** Gestionar Perfil de Usuario y Preferencias (`GET /api/users/me`, `PUT /api/users/me`, `PATCH /api/users/me/preferences`)
- **CU-03:** Publicar Experiencia — Gestión de eventos, aforos y precios (`POST /api/experiences`, `PUT /api/experiences/{id}`, `PATCH /api/experiences/{id}/cancel`, `GET /api/experiences/me/hosted`)
- **CU-04:** Explorar y Filtrar Experiencias — Catálogo web y móvil por geolocalización (`GET /api/experiences/catalog`)

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
    expose_headers=[REQUEST_ID_HEADER],
)
app.add_middleware(
    RequestIdMiddleware,
    service=settings.PROJECT_NAME,
    version=settings.VERSION,
)
install_diagnostic_handlers(app, service=settings.PROJECT_NAME, version=settings.VERSION)

# Registro de routers por paquetes
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(users_router, prefix=settings.API_V1_STR)
from app.admin.controller import admin_router  # noqa: E402

app.include_router(admin_router, prefix=settings.API_V1_STR)

app.include_router(experience_router, prefix=settings.API_V1_STR)
app.include_router(category_router, prefix=settings.API_V1_STR)
app.include_router(venue_router, prefix=settings.API_V1_STR)

app.include_router(booking_router, prefix=settings.API_V1_STR)
app.include_router(payment_router, prefix=settings.API_V1_STR)
app.include_router(subscription_router, prefix=settings.API_V1_STR)

app.include_router(matching_router, prefix=settings.API_V1_STR)
app.include_router(demand_router, prefix=settings.API_V1_STR)
app.include_router(notification_router, prefix=settings.API_V1_STR)

app.include_router(live_router, prefix=settings.API_V1_STR)
app.include_router(report_router, prefix=settings.API_V1_STR)
app.include_router(age_distribution_router, prefix=settings.API_V1_STR)
# HU-17: consola de telemetría en vivo (import local para no alterar el bloque de imports compartido)
from app.live.control.live_telemetry_controller import live_telemetry_router  # noqa: E402

app.include_router(live_telemetry_router, prefix=settings.API_V1_STR)

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
            "CU-01: Autenticación (Registro / Login / Logout / Refresh con JWT)",
            "CU-02: Gestionar Perfil de Usuario y Preferencias",
            "CU-03: Publicar Experiencia (Gestión de eventos, aforos y precios)",
            "CU-04: Explorar y Filtrar Experiencias (Catálogo web y móvil por geolocalización)",
        ],
        swagger_ui="/docs",
        redoc="/redoc",
        openapi_schema="/openapi.json",
    )


@app.get("/health/live", tags=["Health Check"], summary="Verificar que el proceso está activo")
def liveness_check() -> dict[str, str]:
    """Comprueba el proceso sin consultar dependencias externas."""
    return {"status": "live", "service": settings.PROJECT_NAME, "version": settings.VERSION}


@app.get(
    "/health/ready",
    response_model=None,
    tags=["Health Check"],
    summary="Verificar disponibilidad de dependencias",
)
def readiness_check(request: Request) -> JSONResponse:
    """Comprueba PostgreSQL con una consulta de solo lectura y sin alterar `/`."""
    request_id = getattr(request.state, "request_id", None)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        log_diagnostic_event(
            event="readiness.dependency_unavailable",
            service=settings.PROJECT_NAME,
            version=settings.VERSION,
            request_id=request_id,
            error_code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            cause_status=CauseStatus.HYPOTHESIS,
            evidence={
                "dependency": "postgresql",
                "phase": "readiness",
                "exception_type": type(exc).__name__,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_payload(
                "Dependencia requerida no disponible.",
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                request_id,
            ),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ready", "service": settings.PROJECT_NAME, "version": settings.VERSION},
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)
    if _prebound_socket is not None:
        server.run(sockets=[_prebound_socket])
    else:
        server.run()
