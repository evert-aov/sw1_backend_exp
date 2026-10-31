from __future__ import annotations

from datetime import datetime
from app.experience.entity.experience import Experience
from app.matching.dto.matching_dto import (
    ExperienceRecommendationDTO,
    MatchingGroupResponseDTO,
)
from app.matching.entity.matching_group import MatchingGroup, MatchingGroupStatusEnum


class MatchingMapper:
    """
    Componente Mapper para transformar entre entidades de Matching / Experiencias
    y contratos de transferencia DTO (MatchingGroupResponseDTO, ExperienceRecommendationDTO).

    Responsabilidad única: mapeo y ensamblado puro sin consultar base de datos
    ni calcular reglas de negocio del dominio.
    """

    @staticmethod
    def to_group_response_dto(
        group: MatchingGroup,
        target_quorum: int,
        current_members: int,
        is_quorum_reached: bool,
        is_member: bool | None = None,
        affinity_score: float | None = None,
        paid_seats: int | None = None,
        experience_confirmed: bool | None = None,
    ) -> MatchingGroupResponseDTO:
        """
        Convierte una entidad `MatchingGroup` y sus métricas calculadas en un `MatchingGroupResponseDTO`.

        Args:
            group (MatchingGroup): Entidad ORM del grupo de matching.
            target_quorum (int): Meta mínima de reservas pagadas de la experiencia.
            current_members (int): Cantidad de usuarios postulados al grupo.
            is_quorum_reached (bool): Bandera calculada por el servicio indicando si se alcanzó el quórum.
            is_member (bool | None): Indica si el usuario consultante es miembro del grupo.
            affinity_score (float | None): Puntaje de afinidad calculado opcional.
            paid_seats (int | None): Cupos efectivamente pagados de la experiencia.
            experience_confirmed (bool | None): Si la experiencia está confirmada económicamente.

        Returns:
            MatchingGroupResponseDTO: Contrato DTO serializado.
        """
        return MatchingGroupResponseDTO(
            id=group.id,
            experience_id=group.experience_id,
            target_quorum=target_quorum,
            current_members=current_members,
            status=(
                MatchingGroupStatusEnum.REACHED
                if is_quorum_reached
                else group.status
            ),
            deadline=group.deadline,
            created_at=group.created_at,
            is_quorum_reached=is_quorum_reached,
            is_member=bool(is_member),
            affinity_score=float(affinity_score or 0.0),
            paid_slots=int(paid_seats or 0),
            experience_confirmed=bool(experience_confirmed),
        )

    @staticmethod
    def to_recommendation_dto(
        experience: Experience,
        event_date: datetime,
        interest_score: float,
        matched_interests: list[str],
        reasons: list[str],
        distance_km: float | None = None,
    ) -> ExperienceRecommendationDTO:
        """
        Convierte una entidad `Experience` y sus métricas de recomendación calculadas
        en un `ExperienceRecommendationDTO`.

        Args:
            experience (Experience): Entidad ORM de la experiencia.
            event_date (datetime): Fecha del evento normalizada a UTC.
            interest_score (float): Puntuación de afinidad calculada.
            matched_interests (list[str]): Intereses coincidentes.
            reasons (list[str]): Razones descriptivas de la recomendación.
            distance_km (float | None): Distancia calculada en km, si aplica.

        Returns:
            ExperienceRecommendationDTO: Contrato de recomendación serializado.
        """
        venue = experience.venue
        return ExperienceRecommendationDTO(
            experience_id=experience.id,
            title=experience.title,
            category_name=experience.category.name if experience.category else None,
            cover_image_url=experience.cover_image_url,
            modality=getattr(experience.modality, "value", str(experience.modality)),
            event_date=event_date,
            price=experience.price,
            venue_name=venue.name if venue else None,
            venue_zone=venue.zone if venue else None,
            distance_km=distance_km,
            interest_score=interest_score,
            matched_interests=matched_interests,
            reasons=reasons,
        )
