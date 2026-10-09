from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.experience.entity.experience import ModalityEnum, ExperienceStatusEnum


# DTO para detalles de Categoría
class CategoryDTO(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    icon_name: Optional[str] = None

    class Config:
        from_attributes = True


class CategoryCreateDTO(BaseModel):
    name: str
    description: Optional[str] = None
    icon_name: Optional[str] = None


# DTO para detalles y creación de Establecimiento/Venue
class VenueDTO(BaseModel):
    id: int
    owner_id: Optional[int] = None
    name: str
    address: Optional[str] = None
    city: str
    zone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    max_capacity: int
    phone: Optional[str] = None

    class Config:
        from_attributes = True


class VenueCreateDTO(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = "Santa Cruz de la Sierra"
    zone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    max_capacity: Optional[int] = 50
    phone: Optional[str] = None


# DTOs para Experiencias (CU-03, CU-04, CU-05)
class ExperienceCreateDTO(BaseModel):
    category_id: int
    venue_id: Optional[int] = None
    title: str
    description: str
    cover_image_url: Optional[str] = None
    modality: ModalityEnum = ModalityEnum.IN_PERSON
    price: float
    min_capacity: int
    max_capacity: int
    event_date: datetime
    duration_minutes: Optional[int] = 120
    virtual_meeting_url: Optional[str] = None


class ExperienceUpdateDTO(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    modality: Optional[ModalityEnum] = None
    status: Optional[ExperienceStatusEnum] = None
    price: Optional[float] = None
    min_capacity: Optional[int] = None
    max_capacity: Optional[int] = None
    event_date: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    virtual_meeting_url: Optional[str] = None


class ExperienceFilterDTO(BaseModel):
    category_id: Optional[int] = None
    modality: Optional[ModalityEnum] = None
    zone: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    max_price: Optional[float] = None
    only_available: bool = True


class ExperienceResponseDTO(BaseModel):
    id: int
    host_id: int
    category_id: int
    venue_id: Optional[int] = None
    title: str
    description: str
    cover_image_url: Optional[str] = None
    modality: ModalityEnum
    status: ExperienceStatusEnum
    price: float
    min_capacity: int
    max_capacity: int
    reserved_slots: int
    event_date: datetime
    duration_minutes: int
    virtual_meeting_url: Optional[str] = None
    is_quorum_reached: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class CatalogResponseDTO(BaseModel):
    total: int
    experiences: List[ExperienceResponseDTO]
