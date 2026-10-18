from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.experience.entity.experience import ExperienceStatusEnum, ModalityEnum


class CategoryDTO(BaseModel):
    """
    Contrato de respuesta para los detalles de una categoría temática de experiencias (CU-04, CU-05).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Identificador único de la categoría")
    name: str = Field(..., description="Nombre de la categoría temática")
    description: str | None = Field(default=None, description="Descripción de la categoría")
    icon_name: str | None = Field(default=None, description="Identificador de ícono para UI web y móvil")


class CategoryCreateDTO(BaseModel):
    """
    Contrato de datos de entrada para crear una nueva categoría temática (CU-04).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=2, max_length=100, description="Nombre único de la categoría")
    description: str | None = Field(default=None, max_length=500, description="Descripción temática")
    icon_name: str | None = Field(default=None, max_length=100, description="Nombre del ícono Material/Lucide")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Valida que el nombre de la categoría tenga al menos 2 caracteres válidos."""
        clean = v.strip()
        if len(clean) < 2:
            raise ValueError("El nombre de la categoría debe tener al menos 2 caracteres.")
        return clean


class VenueDTO(BaseModel):
    """
    Contrato de respuesta con la información y coordenadas geográficas de un establecimiento (CU-04, CU-05).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Identificador único del establecimiento")
    owner_id: int | None = Field(default=None, description="ID del usuario propietario (rol VENUE)")
    name: str = Field(..., description="Nombre comercial del establecimiento")
    address: str | None = Field(default=None, description="Dirección física del local")
    city: str = Field(..., description="Ciudad donde se ubica el establecimiento")
    zone: str | None = Field(default=None, description="Zona urbana (ej. Equipetrol, Manzana 40, Centro)")
    latitude: float | None = Field(default=None, description="Latitud geográfica (-90 a 90)")
    longitude: float | None = Field(default=None, description="Longitud geográfica (-180 a 180)")
    max_capacity: int = Field(..., description="Aforo máximo físico permitido en el establecimiento")
    phone: str | None = Field(default=None, description="Teléfono de contacto del establecimiento")


class VenueCreateDTO(BaseModel):
    """
    Contrato de datos de entrada para registrar un nuevo establecimiento físico geolocalizado (CU-04, CU-05).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=2, max_length=150, description="Nombre comercial del local")
    address: str | None = Field(default=None, max_length=255, description="Dirección física")
    city: str | None = Field(default="Santa Cruz de la Sierra", max_length=100, description="Ciudad")
    zone: str | None = Field(default=None, max_length=100, description="Zona o barrio urbano")
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0, description="Latitud GPS")
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0, description="Longitud GPS")
    max_capacity: int | None = Field(default=50, ge=1, le=50000, description="Capacidad máxima de personas")
    phone: str | None = Field(default=None, max_length=20, description="Teléfono del establecimiento")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Verifica que el nombre del establecimiento no sea vacío."""
        clean = v.strip()
        if len(clean) < 2:
            raise ValueError("El nombre del local no puede estar vacío.")
        return clean


class ExperienceCreateDTO(BaseModel):
    """
    Contrato de datos de entrada para publicar una nueva experiencia con control de aforos y precios (CU-04 / HU-04).
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "category_id": 1,
                "venue_id": 1,
                "title": "Cata Sensorial de Café de Especialidad y Maridaje",
                "description": "Experiencia guiada por baristas profesionales probando granos de altura y métodos de filtrado.",
                "cover_image_url": "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=800",
                "modality": "IN_PERSON",
                "price": 120.0,
                "min_capacity": 6,
                "max_capacity": 20,
                "event_date": "2026-11-15T19:00:00Z",
                "duration_minutes": 120,
                "virtual_meeting_url": None,
            }
        },
    )

    category_id: int = Field(..., ge=1, description="ID de la categoría temática")
    venue_id: int | None = Field(
        default=None,
        ge=1,
        description="ID del establecimiento físico (requerido en modalidades IN_PERSON e HYBRID)",
    )
    title: str = Field(..., min_length=3, max_length=200, description="Título comercial de la experiencia")
    description: str = Field(..., min_length=10, description="Descripción detallada de la actividad")
    cover_image_url: str | None = Field(
        default=None,
        max_length=255,
        description="URL de la imagen de portada del evento",
    )
    modality: ModalityEnum = Field(
        default=ModalityEnum.IN_PERSON,
        description="Modalidad del evento: IN_PERSON, VIRTUAL o HYBRID",
    )
    price: float = Field(default=0.0, ge=0.0, description="Precio unitario por cupo (0.0 para eventos gratuitos)")
    min_capacity: int = Field(
        ...,
        ge=1,
        le=10000,
        description="Aforo mínimo (quórum requerido para confirmar la realización del evento)",
    )
    max_capacity: int = Field(
        ...,
        ge=1,
        le=10000,
        description="Cupo límite máximo de participantes permitidos",
    )
    event_date: datetime = Field(..., description="Fecha y hora de inicio del evento (debe ser futura)")
    duration_minutes: int | None = Field(
        default=120,
        ge=15,
        le=1440,
        description="Duración estimada de la experiencia en minutos",
    )
    virtual_meeting_url: str | None = Field(
        default=None,
        max_length=255,
        description="Enlace de sala virtual para modalidades VIRTUAL o HYBRID",
    )

    @field_validator("title", "description")
    @classmethod
    def validate_not_blank(cls, v: str) -> str:
        """Asegura que ni el título ni la descripción contengan únicamente espacios en blanco."""
        clean = v.strip()
        if not clean:
            raise ValueError("El campo no puede contener solo espacios en blanco.")
        return clean


class ExperienceUpdateDTO(BaseModel):
    """
    Contrato de datos para actualizar una experiencia existente (CU-04 / HU-04).
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=200, description="Título actualizado")
    description: str | None = Field(default=None, min_length=10, description="Descripción actualizada")
    cover_image_url: str | None = Field(default=None, max_length=255, description="URL de imagen de portada")
    modality: ModalityEnum | None = Field(default=None, description="Modalidad actualizada")
    venue_id: int | None = Field(default=None, ge=1, description="ID del establecimiento físico")
    price: float | None = Field(
        default=None,
        ge=0.0,
        description="Precio por entrada (bloqueado si ya existen reservas vendidas)",
    )
    min_capacity: int | None = Field(default=None, ge=1, le=10000, description="Nuevo aforo mínimo (quórum)")
    max_capacity: int | None = Field(default=None, ge=1, le=10000, description="Nuevo cupo límite máximo")
    event_date: datetime | None = Field(default=None, description="Nueva fecha y hora futura del evento")
    duration_minutes: int | None = Field(default=None, ge=15, le=1440, description="Duración en minutos")
    virtual_meeting_url: str | None = Field(default=None, max_length=255, description="URL de sala virtual")

    @field_validator("title", "description")
    @classmethod
    def validate_optional_not_blank(cls, v: str | None) -> str | None:
        """Valida que los campos opcionales de texto no sean cadenas en blanco si se envían."""
        if v is not None:
            clean = v.strip()
            if not clean:
                raise ValueError("El campo no puede contener solo espacios en blanco.")
            return clean
        return v


class ExperienceFilterDTO(BaseModel):
    """
    Contrato de parámetros de filtrado y búsqueda geoespacial del catálogo de experiencias (CU-05 / HU-05).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    category_id: int | None = Field(default=None, description="Filtrar por ID de categoría temática")
    modality: ModalityEnum | None = Field(
        default=None,
        description="Filtrar por modalidad: IN_PERSON, VIRTUAL o HYBRID",
    )
    zone: str | None = Field(default=None, description="Filtrar por zona urbana (ej. Equipetrol, Manzana 40)")
    latitude: float | None = Field(
        default=None,
        ge=-90.0,
        le=90.0,
        description="Latitud actual del usuario para búsqueda por proximidad geográfica",
    )
    longitude: float | None = Field(
        default=None,
        ge=-180.0,
        le=180.0,
        description="Longitud actual del usuario para búsqueda por proximidad geográfica",
    )
    radius_km: float | None = Field(
        default=None,
        gt=0.0,
        description="Radio de búsqueda en kilómetros desde la ubicación del usuario (Haversine)",
    )
    search: str | None = Field(
        default=None,
        max_length=100,
        description="Búsqueda por texto libre en título o descripción",
    )
    date_from: datetime | None = Field(default=None, description="Filtrar eventos desde esta fecha/hora")
    date_to: datetime | None = Field(default=None, description="Filtrar eventos hasta esta fecha/hora")
    max_price: float | None = Field(default=None, ge=0.0, description="Precio máximo por cupo")
    only_available: bool = Field(
        default=True,
        description="Si es True, muestra únicamente experiencias con cupos disponibles",
    )
    page: int = Field(default=1, ge=1, description="Número de página a consultar")
    page_size: int = Field(default=10, ge=1, le=50, description="Cantidad de experiencias por página")


class ExperienceResponseDTO(BaseModel):
    """
    Contrato de respuesta detallado de una experiencia publicada, incluyendo métricas de quórum,
    geolocalización del local y desglose financiero de comisiones para el anfitrión (CU-04, CU-05 / HU-04, HU-05, HU-07).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="ID único de la experiencia")
    host_id: int = Field(..., description="ID del usuario anfitrión")
    category_id: int = Field(..., description="ID de la categoría temática")
    venue_id: int | None = Field(default=None, description="ID del establecimiento físico asociado")

    category_name: str | None = Field(default=None, description="Nombre de la categoría")
    venue_name: str | None = Field(default=None, description="Nombre del establecimiento físico")
    venue_zone: str | None = Field(default=None, description="Zona urbana del establecimiento")
    venue_address: str | None = Field(default=None, description="Dirección física del establecimiento")
    venue_city: str | None = Field(default=None, description="Ciudad del establecimiento")
    venue_latitude: float | None = Field(default=None, description="Latitud geográfica del establecimiento")
    venue_longitude: float | None = Field(default=None, description="Longitud geográfica del establecimiento")
    distance_km: float | None = Field(
        default=None,
        description="Distancia en kilómetros respecto a la ubicación buscada (cuando se filtra por GPS)",
    )
    host_name: str | None = Field(default=None, description="Nombre completo del anfitrión")

    title: str = Field(..., description="Título de la experiencia")
    description: str = Field(..., description="Descripción completa de la experiencia")
    cover_image_url: str | None = Field(default=None, description="URL de la imagen de portada")
    modality: ModalityEnum = Field(..., description="Modalidad: IN_PERSON, VIRTUAL o HYBRID")
    status: ExperienceStatusEnum = Field(..., description="Estado actual: DRAFT, OPEN, CONFIRMED, LIVE, FINISHED, CANCELLED")
    price: float = Field(..., description="Precio unitario por entrada")
    min_capacity: int = Field(..., description="Aforo mínimo requerido (quórum)")
    max_capacity: int = Field(..., description="Aforo máximo permitido")
    reserved_slots: int = Field(..., description="Cantidad de cupos reservados actualmente")
    available_slots: int = Field(default=0, description="Cantidad de cupos disponibles restantes")
    event_date: datetime = Field(..., description="Fecha y hora programada del evento (UTC)")
    duration_minutes: int = Field(..., description="Duración del evento en minutos")
    virtual_meeting_url: str | None = Field(default=None, description="URL de la sala virtual")
    is_quorum_reached: bool = Field(default=False, description="Indica si ya se alcanzó el cupo mínimo")

    # Desglose financiero y comisiones para el Host (HU-07)
    commission_rate: float = Field(default=0.10, description="Tasa de comisión retenida por la plataforma (ej. 0.10 = 10%)")
    net_price_per_ticket: float = Field(default=0.0, description="Ingreso neto percibido por el host por cada entrada")
    projected_gross_at_quorum: float = Field(default=0.0, description="Ingreso bruto proyectado al completar el quórum mínimo")
    projected_net_at_quorum: float = Field(default=0.0, description="Ganancia neta proyectada al alcanzar el quórum mínimo")
    projected_gross_at_capacity: float = Field(default=0.0, description="Ingreso bruto proyectado a lleno total")
    projected_net_at_capacity: float = Field(default=0.0, description="Ganancia neta proyectada a lleno total")

    created_at: datetime = Field(..., description="Fecha de publicación del registro")


class CatalogResponseDTO(BaseModel):
    """
    Contrato de respuesta paginado para la exploración y filtrado del catálogo de experiencias (CU-05 / HU-05).
    """

    model_config = ConfigDict(from_attributes=True)

    total: int = Field(..., description="Total de experiencias que coinciden con los filtros aplicados")
    page: int = Field(default=1, description="Página actual consultada")
    page_size: int = Field(default=10, description="Tamaño de página solicitado")
    total_pages: int = Field(default=1, description="Cantidad total de páginas disponibles")
    experiences: list[ExperienceResponseDTO] = Field(
        default_factory=list,
        description="Lista de experiencias de la página actual",
    )
