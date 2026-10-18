from __future__ import annotations

import math
from datetime import timezone
from app.core.config import settings
from app.experience.dto.experience_dto import ExperienceCreateDTO, ExperienceResponseDTO
from app.experience.entity.experience import Experience, ExperienceStatusEnum


class ExperienceMapper:
    """
    Encapsula la transformación bidireccional entre la entidad ORM `Experience` (SQLAlchemy)
    y los contratos de transferencia `ExperienceCreateDTO` / `ExperienceResponseDTO` (Pydantic v2),
    incluyendo cálculos financieros de comisiones (HU-07) y distancia Haversine (CU-05).
    """

    @staticmethod
    def calculate_haversine_km(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """
        Calcula la distancia ortodrómica en kilómetros entre dos coordenadas GPS mediante la fórmula de Haversine.

        Args:
            lat1 (float): Latitud de origen en grados decimales.
            lon1 (float): Longitud de origen en grados decimales.
            lat2 (float): Latitud de destino en grados decimales.
            lon2 (float): Longitud de destino en grados decimales.

        Returns:
            float: Distancia en kilómetros redondeada a 2 decimales.
        """
        r_earth_km = 6371.0088
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        a = max(0.0, min(1.0, a))
        c = 2.0 * math.asin(math.sqrt(a))
        return round(r_earth_km * c, 2)

    @staticmethod
    def to_entity(dto: ExperienceCreateDTO, host_id: str) -> Experience:
        """
        Convierte un `ExperienceCreateDTO` en una entidad relacional `Experience` con valores iniciales.

        Args:
            dto (ExperienceCreateDTO): Datos de creación del evento.
            host_id (str): ID (UUID) del usuario anfitrión creador.

        Returns:
            Experience: Entidad ORM inicializada en estado `OPEN`.
        """
        return Experience(
            host_id=host_id,
            category_id=dto.category_id,
            venue_id=dto.venue_id,
            title=dto.title.strip(),
            description=dto.description.strip(),
            cover_image_url=dto.cover_image_url,
            modality=dto.modality,
            status=ExperienceStatusEnum.OPEN,
            price=dto.price,
            min_capacity=dto.min_capacity,
            max_capacity=dto.max_capacity,
            reserved_slots=0,
            event_date=dto.event_date,
            duration_minutes=dto.duration_minutes or 120,
            virtual_meeting_url=dto.virtual_meeting_url,
        )

    @staticmethod
    def to_response_dto(
        exp: Experience,
        commission_percentage: float | None = None,
        user_latitude: float | None = None,
        user_longitude: float | None = None,
    ) -> ExperienceResponseDTO:
        """
        Convierte una entidad `Experience` en un `ExperienceResponseDTO` enriquecido con nombres
        de relaciones, cálculo de quórum, proyecciones financieras del anfitrión y distancia GPS.

        Args:
            exp (Experience): Entidad ORM `Experience`.
            commission_percentage (float | None): Porcentaje de comisión opcional a aplicar.
            user_latitude (float | None): Latitud del usuario para calcular `distance_km`.
            user_longitude (float | None): Longitud del usuario para calcular `distance_km`.

        Returns:
            ExperienceResponseDTO: Contrato de respuesta completo para API web y móvil.
        """
        is_quorum = exp.reserved_slots >= exp.min_capacity
        available_slots = max(0, exp.max_capacity - exp.reserved_slots)
        event_date = exp.event_date
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        else:
            event_date = event_date.astimezone(timezone.utc)

        cat_name = exp.category.name if exp.category else None
        v_name = exp.venue.name if exp.venue else None
        v_zone = exp.venue.zone if exp.venue else None
        v_address = exp.venue.address if exp.venue else None
        v_city = exp.venue.city if exp.venue else None
        v_lat = exp.venue.latitude if exp.venue else None
        v_lon = exp.venue.longitude if exp.venue else None
        h_name = (
            f"{exp.host.first_name} {exp.host.last_name or ''}".strip()
            if exp.host
            else None
        )

        distance_km: float | None = None
        if (
            user_latitude is not None
            and user_longitude is not None
            and v_lat is not None
            and v_lon is not None
        ):
            distance_km = ExperienceMapper.calculate_haversine_km(
                user_latitude, user_longitude, v_lat, v_lon
            )

        fee_percentage = (
            commission_percentage
            if commission_percentage is not None
            else settings.PLATFORM_FEE_PERCENTAGE
        )
        commission_rate = fee_percentage / 100.0
        net_price_per_ticket = round(exp.price * (1.0 - commission_rate), 2)

        return ExperienceResponseDTO(
            id=exp.id,
            host_id=exp.host_id,
            category_id=exp.category_id,
            venue_id=exp.venue_id,
            category_name=cat_name,
            venue_name=v_name,
            venue_zone=v_zone,
            venue_address=v_address,
            venue_city=v_city,
            venue_latitude=v_lat,
            venue_longitude=v_lon,
            distance_km=distance_km,
            host_name=h_name,
            title=exp.title,
            description=exp.description,
            cover_image_url=exp.cover_image_url,
            modality=exp.modality,
            status=exp.status,
            price=exp.price,
            min_capacity=exp.min_capacity,
            max_capacity=exp.max_capacity,
            reserved_slots=exp.reserved_slots,
            available_slots=available_slots,
            event_date=event_date,
            duration_minutes=exp.duration_minutes or 120,
            virtual_meeting_url=exp.virtual_meeting_url,
            is_quorum_reached=is_quorum,
            commission_rate=commission_rate,
            net_price_per_ticket=net_price_per_ticket,
            projected_gross_at_quorum=round(exp.price * exp.min_capacity, 2),
            projected_net_at_quorum=round(net_price_per_ticket * exp.min_capacity, 2),
            projected_gross_at_capacity=round(exp.price * exp.max_capacity, 2),
            projected_net_at_capacity=round(net_price_per_ticket * exp.max_capacity, 2),
            created_at=exp.created_at,
        )
