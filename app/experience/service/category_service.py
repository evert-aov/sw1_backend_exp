from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.experience.dto.experience_dto import CategoryCreateDTO, CategoryDTO
from app.experience.mapper.category_mapper import CategoryMapper
from app.experience.repository.category_repository import CategoryRepository


class CategoryService:
    """
    Servicio de negocio para la administración y consulta de categorías temáticas de experiencias.
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el servicio de categorías con su repositorio colaborador.

        Args:
            db (Session): Sesión activa de SQLAlchemy.
        """
        self.db = db
        self.category_repo = CategoryRepository(db)

    def get_all_categories(self) -> list[CategoryDTO]:
        """
        Recupera todas las categorías temáticas registradas en la plataforma.

        Returns:
            list[CategoryDTO]: Lista de categorías ordenadas alfabéticamente.
        """
        categories = self.category_repo.get_all()
        return [CategoryMapper.to_dto(c) for c in categories]

    def get_category_by_id(self, category_id: int) -> CategoryDTO:
        """
        Consulta el detalle de una categoría temática por su identificador único.

        Args:
            category_id (int): ID de la categoría.

        Returns:
            CategoryDTO: Datos de la categoría encontrada.

        Raises:
            HTTPException (404): Si la categoría no existe.
        """
        category = self.category_repo.get_by_id(category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La categoría con ID {category_id} no fue encontrada",
            )
        return CategoryMapper.to_dto(category)

    def create_category(self, dto: CategoryCreateDTO) -> CategoryDTO:
        """
        Registra una nueva categoría temática verificando que su nombre no esté duplicado.

        Args:
            dto (CategoryCreateDTO): Datos de la nueva categoría.

        Returns:
            CategoryDTO: Categoría creada y persistida.

        Raises:
            HTTPException (400): Si ya existe una categoría con el mismo nombre.
        """
        existing = self.category_repo.get_by_name(dto.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La categoría '{dto.name}' ya se encuentra registrada",
            )
        category = CategoryMapper.to_entity(dto)
        created = self.category_repo.create(category)
        return CategoryMapper.to_dto(created)
