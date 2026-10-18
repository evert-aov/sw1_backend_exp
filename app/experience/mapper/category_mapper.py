from __future__ import annotations

from app.experience.dto.experience_dto import CategoryCreateDTO, CategoryDTO
from app.experience.entity.category import Category


class CategoryMapper:
    """
    Componente Mapper para transformar entre la entidad ORM `Category`
    y sus contratos de transferencia `CategoryDTO` / `CategoryCreateDTO`.
    """

    @staticmethod
    def to_entity(dto: CategoryCreateDTO) -> Category:
        """
        Convierte un `CategoryCreateDTO` en una entidad relacional `Category`.

        Args:
            dto (CategoryCreateDTO): Datos de entrada para crear la categoría.

        Returns:
            Category: Instancia ORM lista para persistir.
        """
        return Category(
            name=dto.name.strip(),
            description=dto.description,
            icon_name=dto.icon_name,
        )

    @staticmethod
    def to_dto(category: Category) -> CategoryDTO:
        """
        Convierte una entidad relacional `Category` en un `CategoryDTO`.

        Args:
            category (Category): Entidad ORM `Category`.

        Returns:
            CategoryDTO: Contrato de respuesta validado.
        """
        return CategoryDTO.model_validate(category)
