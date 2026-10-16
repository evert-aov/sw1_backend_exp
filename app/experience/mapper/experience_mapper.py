from datetime import timezone
from typing import Optional
from app.core.config import settings
from app.experience.entity.experience import Experience, ExperienceStatusEnum
from app.experience.dto.experience_dto import ExperienceCreateDTO, ExperienceResponseDTO


class ExperienceMapper:
    """
    Encapsula la transformación bidireccional entre Entidades ORM (SQLAlchemy)
    y Contratos de Transferencia de Datos (DTOs Pydantic)
    """

    @staticmethod
    def to_entity(dto: ExperienceCreateDTO, host_id: int) -> Experience:
        """Convierte un DTO de creación en una entidad relacional Experience con valores iniciales."""
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
        commission_percentage: Optional[float] = None,
    ) -> ExperienceResponseDTO:
        is_quorum = (exp.reserved_slots >= exp.min_capacity)
        event_date = exp.event_date
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        else:
            event_date = event_date.astimezone(timezone.utc)

        cat_name = exp.category.name if exp.category else None
        v_name = exp.venue.name if exp.venue else None
        v_zone = exp.venue.zone if exp.venue else None
        h_name = f"{exp.host.first_name} {exp.host.last_name or ''}".strip() if exp.host else None

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
