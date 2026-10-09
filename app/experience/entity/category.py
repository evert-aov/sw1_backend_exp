from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


# Entidad Categoría: clasificación temática de experiencias (Gastronomía, Arte, Música, etc.)
class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    icon_name = Column(String(100), nullable=True)

    experiences = relationship("Experience", back_populates="category")
