from app.experience.dto.experience_dto import CategoryDTO, CategoryCreateDTO
from app.experience.entity.category import Category


class CategoryMapper:

    @staticmethod
    def to_entity(dto: CategoryCreateDTO) -> Category:
        """Convierte un CategoryCreateDTO en una entidad relacional Category."""
        return Category(
            name=dto.name.strip(),
            description=dto.description,
            icon_name=dto.icon_name,
        )

    @staticmethod
    def to_dto(category: Category) -> CategoryDTO:
        """Convierte una entidad relacional Category en un CategoryDTO."""
        return CategoryDTO.model_validate(category)
