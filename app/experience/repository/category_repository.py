from typing import Optional, List
from sqlalchemy.orm import Session
from app.experience.entity.category import Category


# Repositorio para la entidad Category: únicamente firmas de métodos
class CategoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, category_id: int) -> Optional[Category]:
        # Buscar categoría por ID
        pass

    def get_by_name(self, name: str) -> Optional[Category]:
        # Buscar categoría por nombre
        pass

    def create(self, category: Category) -> Category:
        # Crear nueva categoría temática
        pass

    def get_all(self) -> List[Category]:
        # Listar todas las categorías disponibles
        pass
