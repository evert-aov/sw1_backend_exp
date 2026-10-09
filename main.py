from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

# Importación de routers por paquetes
from app.auth.control import auth_router, users_router
from app.experience.control import experience_router, category_router
from app.booking.control import booking_router, payment_router, subscription_router
from app.matching.control import matching_router, demand_router
from app.live.control import live_router, report_router

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API de la plataforma EXPERIENCIA - Arquitectura en Capas",
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


@app.get("/")
def health_check():
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
    }
