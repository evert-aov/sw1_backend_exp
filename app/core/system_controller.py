from __future__ import annotations

from typing import Any
from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field
from app.core.database import reset_and_seed_database, reset_database, seed_database


class SystemResetResponseDTO(BaseModel):
    """
    Contrato de respuesta al reiniciar la base de datos en cascada.
    """

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(default="success", description="Estado de la operación")
    message: str = Field(..., description="Detalle del reinicio de tablas")
    tables_recreated: int = Field(..., description="Cantidad de tablas recreadas")


class SystemSeedResponseDTO(BaseModel):
    """
    Contrato de respuesta tras ejecutar el seeder de datos de prueba del Sprint 1.
    """

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(default="success", description="Estado de la operación de seeding")
    message: str = Field(..., description="Mensaje de confirmación")
    roles: list[str] = Field(default_factory=list, description="Roles inicializados")
    users: list[dict[str, Any]] = Field(default_factory=list, description="Usuarios semilla creados")
    categories: list[dict[str, Any]] = Field(default_factory=list, description="Categorías temáticas creadas")
    venues: list[dict[str, Any]] = Field(default_factory=list, description="Establecimientos geolocalizados creados")
    experiences: list[dict[str, Any]] = Field(default_factory=list, description="Experiencias de prueba publicadas")


system_router = APIRouter(prefix="/system", tags=["System & Database Administration"])


@system_router.post(
    "/reset-db",
    response_model=SystemResetResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Vaciar y limpiar la base de datos completa en cascada",
    description="Elimina y recrea todas las 19 tablas en cascada, limpiando también los tokens revocados en memoria.",
    response_description="Confirmación de base de datos reiniciada",
)
def reset_db_endpoint() -> SystemResetResponseDTO:
    """
    Reinicia completamente el esquema relacional de la base de datos eliminando y recreando todas las tablas.

    Returns:
        SystemResetResponseDTO: Resumen del reinicio y número de tablas recreadas.
    """
    from app.core.security import clear_revoked_tokens

    clear_revoked_tokens()
    result = reset_database()
    return SystemResetResponseDTO(**result)


@system_router.post(
    "/seed",
    response_model=SystemSeedResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Poblar roles, usuarios, categorías, locales y experiencias de prueba (Sprint 1)",
    description=(
        "Inserta los 4 roles principales (`ADMIN`, `HOST`, `VENUE`, `ATTENDEE`), usuarios de demostración "
        "con contraseña `Password123!`, categorías temáticas, establecimientos geolocalizados y experiencias "
        "de prueba para verificar CU-01 a CU-05."
    ),
    response_description="Resumen de datos semilla insertados",
)
def seed_db_endpoint() -> SystemSeedResponseDTO:
    """
    Ejecuta el seeder idempotente poblando datos de prueba para todos los casos de uso del Sprint 1.

    Returns:
        SystemSeedResponseDTO: Detalle de roles, usuarios, categorías, locales y experiencias insertadas.
    """
    result = seed_database()
    return SystemSeedResponseDTO(**result)


@system_router.post(
    "/reset-and-seed",
    response_model=SystemSeedResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Limpiar base de datos y poblar seeder completo (1-Click Reset & Seed)",
    description=(
        "Acción combinada: vacía todas las tablas en cascada e inmediatamente inserta todos los datos "
        "semilla de demostración para pruebas integrales del Sprint 1."
    ),
    response_description="Base de datos reiniciada y poblada con datos semilla",
)
def reset_and_seed_endpoint() -> SystemSeedResponseDTO:
    """
    Vacía la base de datos en cascada, limpia sesiones revocadas e inserta todos los datos semilla desde cero.

    Returns:
        SystemSeedResponseDTO: Resumen completo de los datos semilla recreados.
    """
    from app.core.security import clear_revoked_tokens

    clear_revoked_tokens()
    result = reset_and_seed_database()
    return SystemSeedResponseDTO(**result)
