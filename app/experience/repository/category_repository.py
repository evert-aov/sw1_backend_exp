from __future__ import annotations

from sqlalchemy.orm import Session
from app.experience.entity.category import Category


class CategoryRepository:
    """
    Repositorio de acceso a datos para la entidad `Category`.
    Gestiona la persistencia y consulta de categorías temáticas del catálogo (CU-04, CU-05).
    """

    def __init__(self, db: Session) -> None:
        """
        Inicializa el repositorio con la sesión activa de SQLAlchemy.

        Args:
            db (Session): Sesión de base de datos inyectada.
        """
        self.db = db

    def get_by_id(self, category_id: str) -> Category | None:
        """
        Busca una categoría por su identificador único (UUID).

        Args:
            category_id (str): ID (UUID) de la categoría.

        Returns:
            Category | None: Entidad `Category` encontrada o `None`.
        """
        return self.db.query(Category).filter(Category.id == str(category_id)).first()

    def get_by_name(self, name: str) -> Category | None:
        """
        Busca una categoría por coincidencia insensible a mayúsculas/minúsculas de su nombre.

        Args:
            name (str): Nombre de la categoría a buscar.

        Returns:
            Category | None: Entidad `Category` encontrada o `None`.
        """
        return self.db.query(Category).filter(Category.name.ilike(name.strip())).first()

    def create(self, category: Category) -> Category:
        """
        Persiste una nueva categoría temática en la base de datos.

        Args:
            category (Category): Entidad `Category` a guardar.

        Returns:
            Category: Entidad `Category` persistida con su ID asignado.
        """
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category

    def get_all(self) -> list[Category]:
        """
        Recupera todas las categorías temáticas ordenadas alfabéticamente por nombre.

        Returns:
            list[Category]: Lista completa de categorías.
        """
        return self.db.query(Category).order_by(Category.name.asc()).all()
