from typing import Optional, List
from sqlalchemy.orm import Session
from app.experience.entity.category import Category


# Repositorio para la entidad Category: únicamente firmas de métodos
class CategoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, category_id: int) -> Optional[Category]:
        return self.db.query(Category).filter(Category.id == category_id).first()

    def get_by_name(self, name: str) -> Optional[Category]:
        return self.db.query(Category).filter(Category.name.ilike(name.strip())).first()

    def create(self, category: Category) -> Category:
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category

    def get_all(self) -> List[Category]:
        return self.db.query(Category).order_by(Category.name.asc()).all()
