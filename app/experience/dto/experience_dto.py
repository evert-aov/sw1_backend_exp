from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.experience.entity.experience import ModalityEnum, ExperienceStatusEnum


# DTO para detalles de Categoría
class CategoryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    icon_name: Optional[str] = None


class CategoryCreateDTO(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    icon_name: Optional[str] = Field(None, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 2:
            raise ValueError("El nombre de la categoría debe tener al menos 2 caracteres.")
        return clean


# DTO para detalles y creación de Establecimiento/Venue
class VenueDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class VenueCreateDTO(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    zone: Optional[str] = Field(None, max_length=100)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    max_capacity: Optional[int] = Field(50, ge=1, le=50000)
    phone: Optional[str] = Field(None, max_length=20)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 2:
            raise ValueError("El nombre del local no puede estar vacío.")
        return clean


# DTOs para Experiencias (CU-03, CU-04, CU-05)
class ExperienceCreateDTO(BaseModel):
    category_id: int = Field(..., ge=1)
    venue_id: Optional[int] = Field(None, ge=1)
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10)
    cover_image_url: Optional[str] = Field(None, max_length=255)
    modality: ModalityEnum = ModalityEnum.IN_PERSON
    price: float = Field(0.0, ge=0.0)
    min_capacity: int = Field(..., ge=1, le=10000)
    max_capacity: int = Field(..., ge=1, le=10000)
    event_date: datetime
    duration_minutes: Optional[int] = Field(120, ge=15, le=1440)
    virtual_meeting_url: Optional[str] = Field(None, max_length=255)

    @field_validator("title", "description")
    @classmethod
    def validate_not_blank(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("El campo no puede contener solo espacios en blanco.")
        return clean


class ExperienceUpdateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = Field(None, min_length=10)
    cover_image_url: Optional[str] = Field(None, max_length=255)
    modality: Optional[ModalityEnum] = None
    venue_id: Optional[int] = Field(None, ge=1)
    price: Optional[float] = Field(None, ge=0.0)
    min_capacity: Optional[int] = Field(None, ge=1, le=10000)
    max_capacity: Optional[int] = Field(None, ge=1, le=10000)
    event_date: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(None, ge=15, le=1440)
    virtual_meeting_url: Optional[str] = Field(None, max_length=255)

    @field_validator("title", "description")
    @classmethod
    def validate_optional_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not clean:
                raise ValueError("El campo no puede contener solo espacios en blanco.")
            return clean
        return v

class ExperienceFilterDTO(BaseModel):
    category_id: Optional[int] = None
    modality: Optional[ModalityEnum] = None
    zone: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    radius_km: Optional[float] = Field(None, gt=0.0)
    search: Optional[str] = Field(None, max_length=100, description="Búsqueda por texto en título o descripción")
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    max_price: Optional[float] = Field(None, ge=0.0)
    only_available: bool = True
    page: int = Field(1, ge=1)
    page_size: int = Field(10, ge=1, le=50)


class ExperienceResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    host_id: int
    category_id: int
    venue_id: Optional[int] = None

    category_name: Optional[str] = None
    venue_name: Optional[str] = None
    venue_zone: Optional[str] = None
    host_name: Optional[str] = None

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

    # Desglose financiero y comisiones para el Host (HU-07)
    commission_rate: float = Field(0.10, description="Tasa de comisión retenida por la plataforma")
    net_price_per_ticket: float = Field(0.0, description="Ingreso neto percibido por el host por cada entrada")
    projected_gross_at_quorum: float = Field(0.0, description="Ingreso bruto proyectado al completar el quórum mínimo")
    projected_net_at_quorum: float = Field(0.0, description="Ganancia neta proyectada al alcanzar el quórum mínimo")
    projected_gross_at_capacity: float = Field(0.0, description="Ingreso bruto proyectado a lleno total")
    projected_net_at_capacity: float = Field(0.0, description="Ganancia neta proyectada a lleno total")

    created_at: datetime


class CatalogResponseDTO(BaseModel):
    total: int
    page: int = 1
    page_size: int = 10
    total_pages: int = 1
    experiences: List[ExperienceResponseDTO]
