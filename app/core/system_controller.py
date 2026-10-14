from fastapi import APIRouter, status
from app.core.database import reset_database, seed_database, reset_and_seed_database

system_router = APIRouter(prefix="/system", tags=["System & Database Administration"])


@system_router.post(
    "/reset-db",
    status_code=status.HTTP_200_OK,
    summary="Vaciar y limpiar la base de datos completa en cascada",
    description="Elimina y recrea todas las 19 tablas en cascada, reseteando todas las secuencias auto-incrementales a 1.",
)
def reset_db_endpoint():
    return reset_database()


@system_router.post(
    "/seed",
    status_code=status.HTTP_200_OK,
    summary="Poblar roles y usuarios por defecto",
    description="Inserta los 4 roles principales (ADMIN, HOST, VENUE, ATTENDEE) y los usuarios de prueba con contraseña 'Password123!'.",
)
def seed_db_endpoint():
    return seed_database()


@system_router.post(
    "/reset-and-seed",
    status_code=status.HTTP_200_OK,
    summary="Limpiar base de datos y poblar seeder (1-Click Reset & Seed)",
    description="Acción combinada: vacía todas las tablas en cascada e inmediatamente inserta los roles y usuarios de demostración.",
)
def reset_and_seed_endpoint():
    return reset_and_seed_database()
