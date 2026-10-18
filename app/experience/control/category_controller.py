from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.core.database import get_db
from app.core.security import RoleChecker
from app.experience.dto.experience_dto import CategoryCreateDTO, CategoryDTO
from app.experience.service.category_service import CategoryService

category_router = APIRouter(prefix="/categories", tags=["Categories Controller"])


@category_router.get(
    "",
    response_model=list[CategoryDTO],
    status_code=status.HTTP_200_OK,
    summary="Listar todas las categorías temáticas (CU-04, CU-05)",
    description="Obtiene el catálogo completo de categorías temáticas disponibles para clasificar y filtrar experiencias.",
    response_description="Lista de categorías temáticas",
)
def list_categories(
    db: Annotated[Session, Depends(get_db)],
) -> list[CategoryDTO]:
    """
    Lista todas las categorías temáticas disponibles en el sistema.

    Args:
        db (Session): Sesión de base de datos inyectada.

    Returns:
        list[CategoryDTO]: Lista ordenada de categorías temáticas.
    """
    service = CategoryService(db)
    return service.get_all_categories()


@category_router.get(
    "/{category_id}",
    response_model=CategoryDTO,
    status_code=status.HTTP_200_OK,
    summary="Obtener detalle de una categoría por ID",
    description="Consulta la información detallada de una categoría específica mediante su identificador único.",
    response_description="Detalle de la categoría solicitada",
)
def get_category(
    category_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CategoryDTO:
    """
    Obtiene los detalles de una categoría temática por su ID (UUID).

    Args:
        category_id (str): ID de la categoría a consultar.
        db (Session): Sesión de base de datos inyectada.

    Returns:
        CategoryDTO: Datos de la categoría.
    """
    service = CategoryService(db)
    return service.get_category_by_id(category_id)


@category_router.post(
    "",
    response_model=CategoryDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una nueva categoría temática (CU-04)",
    description="Permite a un usuario con rol `ADMIN` o `HOST` registrar una nueva categoría temática.",
    response_description="Categoría creada exitosamente",
)
def create_category(
    dto: CategoryCreateDTO,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(RoleChecker(["ADMIN", "HOST"]))],
) -> CategoryDTO:
    """
    Registra una nueva categoría temática en el catálogo (requiere rol `ADMIN` o `HOST`).

    Args:
        dto (CategoryCreateDTO): Nombre, descripción e ícono de la categoría.
        db (Session): Sesión de base de datos inyectada.
        current_user (User): Usuario autenticado con rol autorizado.

    Returns:
        CategoryDTO: Categoría recién creada.
    """
    service = CategoryService(db)
    return service.create_category(dto)
