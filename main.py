from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from app.core.config import settings
from app.core.database import init_db

# Importación de routers por paquetes
from app.auth.control import auth_router, users_router
from app.experience.control import experience_router, category_router
from app.booking.control import booking_router, payment_router, subscription_router
from app.matching.control import matching_router, demand_router
from app.live.control import live_router, report_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialización y sincronización de base de datos según DB_SYNCHRONIZE
    try:
        init_db()
    except Exception as e:
        print(f"[Database Warning] No se pudo sincronizar automáticamente: {e}")
    yield


# Definición de etiquetas descriptivas para Swagger UI agrupadas por módulos y Casos de Uso
tags_metadata = [
    {
        "name": "Auth Controller (CU-01)",
        "description": "Endpoints para registro de usuarios, validación de credenciales e inicio de sesión con JWT.",
    },
    {
        "name": "Users Controller (CU-02)",
        "description": "Gestión de perfiles de usuario, biografía, avatar y preferencias/etiquetas de interés.",
    },
    {
        "name": "Experience Controller (CU-03, CU-04, CU-05)",
        "description": "Publicación de experiencias con control de aforos y exploración del catálogo con filtros geográficos y de modalidad.",
    },
    {
        "name": "Categories & Venues Controller",
        "description": "Administración de categorías temáticas y espacios físicos/establecimientos comerciales.",
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
]

# Inicialización de la aplicación FastAPI con parámetros personalizados para Swagger UI
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="""
## 🎟️ EXPERIENCIA — API RESTful & WebSockets

Ecosistema tecnológico para conectar usuarios con experiencias presenciales y virtuales de cupo limitado, optimizando la interacción de la audiencia en tiempo real mediante Visión Artificial e IA.

### 🛡️ Seguridad
Para consumir endpoints protegidos:
1. Inicia sesión en `/api/auth/login` para obtener tu **JWT token**.
2. Haz clic en el botón verde **Authorize 🔓** en la parte superior derecha.
3. Ingresa tu token como: `Bearer <tu_token_aqui>`.
    """,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={
        "persistAuthorization": True,          # Recuerda el token JWT al recargar la página
        "displayRequestDuration": True,        # Muestra el tiempo de respuesta en ms de cada petición
        "filter": True,                        # Barra de búsqueda para filtrar endpoints
        "docExpansion": "list",                # Muestra las secciones expandidas por defecto
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

app.include_router(booking_router, prefix=settings.API_V1_STR)
app.include_router(payment_router, prefix=settings.API_V1_STR)
app.include_router(subscription_router, prefix=settings.API_V1_STR)

app.include_router(matching_router, prefix=settings.API_V1_STR)
app.include_router(demand_router, prefix=settings.API_V1_STR)

app.include_router(live_router, prefix=settings.API_V1_STR)
app.include_router(report_router, prefix=settings.API_V1_STR)


def custom_openapi():
    # Personalización del esquema OpenAPI con esquema de seguridad Bearer JWT
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
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Ingresa tu token JWT para autenticar las peticiones.",
        }
    }

    # Aplicar BearerAuth globalmente a todos los endpoints en Swagger UI
    openapi_schema["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/", tags=["Health Check"])
def health_check():
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "swagger_ui": "/docs",
        "redoc": "/redoc",
        "openapi_schema": "/openapi.json",
    }
