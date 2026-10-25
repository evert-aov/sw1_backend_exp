from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from math import inf, isfinite
from typing import ClassVar

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth.repository.user_repository import UserRepository
from app.experience.entity.experience import Experience, ExperienceStatusEnum
from app.experience.mapper.experience_mapper import ExperienceMapper
from app.experience.repository.experience_repository import ExperienceRepository
from app.matching.dto.matching_dto import (
    ExperienceRecommendationDTO,
    MatchingApplicationDTO,
    MatchingGroupResponseDTO,
)
from app.matching.entity.matching_group import MatchingGroup, MatchingGroupStatusEnum
from app.matching.entity.matching_member import MatchingMember
from app.matching.mapper.matching_mapper import MatchingMapper
from app.matching.repository.matching_repository import MatchingRepository


def _normalize_interest_label(label: str) -> str:
    """Normaliza un interés para comparaciones sin acentos ni mayúsculas.

    Args:
        label (str): Etiqueta de interés original.

    Returns:
        str: Etiqueta normalizada y sin espacios externos.
    """
    decomposed = unicodedata.normalize("NFKD", label.casefold())
    return "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).strip()


def _normalize_interest_tags(interests: object) -> set[str]:
    """Extrae etiquetas de interés válidas y normalizadas de un perfil.

    Args:
        interests (object): Valor de intereses almacenado en el perfil.

    Returns:
        set[str]: Intereses únicos o un conjunto vacío si no hay lista válida.
    """
    if not isinstance(interests, list):
        return set()
    return {
        normalized
        for interest in interests
        if isinstance(interest, str)
        if (normalized := _normalize_interest_label(interest))
    }


class MatchingAlgorithmService:
    """Agrupa asistentes compatibles y evalúa el quórum de reservas pagadas."""

    def __init__(self, db: Session):
        """Inicializa servicios de matching con repositorios de la misma sesión.

        Args:
            db (Session): Sesión SQLAlchemy de la petición.
        """
        self.db = db
        self.matching_repo = MatchingRepository(db)
        self.experience_repo = ExperienceRepository(db)
        self.user_repo = UserRepository(db)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        """Normaliza una fecha a UTC, asumiendo UTC si no tiene zona horaria.

        Args:
            value (datetime): Fecha que se va a comparar.

        Returns:
            datetime: Fecha con zona horaria UTC.
        """
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _group_response(
        self,
        group: MatchingGroup,
        experience: Experience,
        current_members: int | None = None,
        paid_seats: int | None = None,
    ) -> MatchingGroupResponseDTO:
        """Construye la respuesta de un grupo con quórum basado en pagos.

        Args:
            group (MatchingGroup): Grupo consultado.
            experience (Experience): Experiencia asociada al grupo.
            current_members (int | None): Postulados precalculados o None para contarlos.
            paid_seats (int | None): Cupos pagados precalculados o None para contarlos.

        Returns:
            MatchingGroupResponseDTO: Estado del grupo con quórum calculado.
        """
        if paid_seats is None:
            paid_seats = self.matching_repo.count_paid_seats(experience.id)
        if current_members is None:
            current_members = self.matching_repo.count_members(group.id)
        quorum_reached = (
            experience.status == ExperienceStatusEnum.CONFIRMED
            or paid_seats >= experience.min_capacity
        )
        return MatchingMapper.to_group_response_dto(
            group=group,
            target_quorum=experience.min_capacity,
            current_members=current_members,
            is_quorum_reached=quorum_reached,
        )

    def apply_for_matching(
        self, user_id: str, dto: MatchingApplicationDTO
    ) -> MatchingGroupResponseDTO:
        """Inscribe al asistente una sola vez en un grupo abierto compatible y no saturado.

        Cada nuevo miembro debe compartir al menos una etiqueta de interés con cada
        miembro existente. La cantidad de miembros expresa interés, nunca reservas
        pagadas ni quórum financiero.

        Args:
            user_id (str): Identificador del asistente que se postula.
            dto (MatchingApplicationDTO): Experiencia a la que solicita unirse.

        Returns:
            MatchingGroupResponseDTO: Grupo asignado y estado actual de quórum.

        Raises:
            HTTPException: Si el usuario no es asistente, la experiencia no existe,
            no está abierta, ya comenzó o agotó sus reservas pagadas.
        """
        user = self.user_repo.get_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
            )
        roles = {role.upper() for role in self.user_repo.get_user_roles(user_id)}
        if "ATTENDEE" not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo un usuario asistente puede postularse a matching.",
            )

        experience = self.matching_repo.get_experience_for_matching(dto.experience_id)
        if experience is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Experiencia no encontrada.",
            )

        existing_group = self.matching_repo.get_member_group(experience.id, user_id)
        if existing_group is not None:
            self.db.commit()
            return self._group_response(existing_group, experience)

        if experience.status != ExperienceStatusEnum.OPEN:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Solo se puede postular a experiencias abiertas.",
            )
        if self._as_utc(experience.event_date) <= datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No se puede postular a una experiencia que ya comenzó.",
            )

        paid_seats = self.matching_repo.count_paid_seats(experience.id)
        if paid_seats >= experience.max_capacity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La experiencia ya alcanzó su capacidad máxima de reservas pagadas.",
            )

        groups = self.matching_repo.get_groups_by_experience(experience.id)
        member_counts = self.matching_repo.get_group_member_counts(experience.id)
        applicant_interests = _normalize_interest_tags(user.interests)
        member_interests = self.matching_repo.get_group_member_interests(
            [candidate.id for candidate in groups]
        )
        normalized_group_interests = {
            group_id: [_normalize_interest_tags(interests) for interests in members]
            for group_id, members in member_interests.items()
        }

        def is_compatible(candidate: MatchingGroup) -> bool:
            existing_members = normalized_group_interests.get(candidate.id, [])
            if not existing_members:
                return True
            return bool(applicant_interests) and all(
                applicant_interests.intersection(interests)
                for interests in existing_members
            )

        group = next(
            (
                candidate
                for candidate in groups
                if candidate.status == MatchingGroupStatusEnum.OPEN
                and member_counts.get(candidate.id, 0) < experience.max_capacity
                and is_compatible(candidate)
            ),
            None,
        )

        try:
            if group is None:
                group = self.matching_repo.create_group(
                    MatchingGroup(
                        experience_id=experience.id,
                        target_quorum=experience.min_capacity,
                        current_members=0,
                        status=MatchingGroupStatusEnum.OPEN,
                        # El esquema legado exige deadline; se informa la fecha del evento,
                        # pero no se expira ni se cierra el grupo automáticamente.
                        deadline=experience.event_date,
                    )
                )
            self.matching_repo.add_member(
                MatchingMember(matching_group_id=group.id, user_id=str(user_id))
            )
            self.db.commit()
            self.db.refresh(group)
        except Exception:
            self.db.rollback()
            raise

        return self._group_response(group, experience)

    def get_group_status(
        self, user_id: str, experience_id: str
    ) -> MatchingGroupResponseDTO:
        """Devuelve el grupo al que se postuló un usuario en una experiencia.

        Args:
            user_id (str): Identificador del usuario que consulta su postulación.
            experience_id (str): Identificador de la experiencia.

        Returns:
            MatchingGroupResponseDTO: Grupo, miembros postulados y quórum pagado.

        Raises:
            HTTPException: Si la experiencia o la postulación no existen.
        """
        experience = self.experience_repo.get_by_id(experience_id)
        if experience is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Experiencia no encontrada.",
            )
        group = self.matching_repo.get_member_group(experience_id, user_id)
        if group is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No tienes una postulación de matching para esta experiencia.",
            )
        return self._group_response(group, experience)

    def get_experience_groups(
        self, experience_id: str
    ) -> list[MatchingGroupResponseDTO]:
        """Lista los grupos de postulación de una experiencia.

        Args:
            experience_id (str): Identificador de la experiencia.

        Returns:
            list[MatchingGroupResponseDTO]: Grupos con postulados y quórum pagado.

        Raises:
            HTTPException: Si la experiencia no existe.
        """
        experience = self.experience_repo.get_by_id(experience_id)
        if experience is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Experiencia no encontrada.",
            )
        groups = self.matching_repo.get_groups_by_experience(experience_id)
        member_counts = self.matching_repo.get_group_member_counts(experience_id)
        paid_seats = self.matching_repo.count_paid_seats(experience_id)
        return [
            self._group_response(
                group,
                experience,
                current_members=member_counts.get(group.id, 0),
                paid_seats=paid_seats,
            )
            for group in groups
        ]

    def evaluate_quorum(self, experience_id: str) -> bool:
        """Confirma la experiencia cuando las reservas pagadas alcanzan el mínimo.

        Debe invocarse después de que el servicio de reservas haya confirmado y
        persistido el pago. El cálculo se rehace desde la base de datos para que
        reintentos de webhooks o llamadas repetidas no dupliquen cupos.

        Args:
            experience_id (str): Identificador de la experiencia evaluada.

        Returns:
            bool: True si quedó confirmada o ya estaba confirmada; False si no
            existe, no está abierta o no alcanzó el mínimo de reservas pagadas.
        """
        experience = self.matching_repo.get_experience_for_quorum(experience_id)
        if experience is None:
            return False

        if experience.status == ExperienceStatusEnum.CONFIRMED:
            self.matching_repo.mark_experience_groups_reached(experience.id)
            self.db.commit()
            return True
        if experience.status != ExperienceStatusEnum.OPEN:
            return False

        paid_seats = self.matching_repo.count_paid_seats(experience.id)
        if paid_seats < experience.min_capacity:
            return False

        experience.status = ExperienceStatusEnum.CONFIRMED
        self.matching_repo.mark_experience_groups_reached(experience.id)
        self.db.commit()
        return True


class ExperienceRecommendationService:
    """Recomendación determinística de experiencias al propio usuario, no de asistentes entre sí."""

    _STOP_WORDS: ClassVar[set[str]] = {
        "a",
        "al",
        "con",
        "de",
        "del",
        "el",
        "en",
        "la",
        "las",
        "los",
        "para",
        "por",
        "un",
        "una",
        "y",
    }

    def __init__(self, db: Session) -> None:
        """Inicializa la recomendación con repositorios de usuario y experiencia.

        Args:
            db (Session): Sesión SQLAlchemy de la petición.
        """
        self.user_repo = UserRepository(db)
        self.experience_repo = ExperienceRepository(db)

    @staticmethod
    def _normalize(text: str) -> str:
        """Normaliza texto temático con la misma regla usada por matching.

        Args:
            text (str): Texto de interés o experiencia.

        Returns:
            str: Texto normalizado para comparar afinidad.
        """
        return _normalize_interest_label(text)

    @classmethod
    def _interest_affinity(
        cls,
        interests: list[str],
        experience: Experience,
    ) -> tuple[float, list[str]]:
        """Calcula afinidad temática y conserva intereses que coinciden.

        Args:
            interests (list[str]): Intereses declarados por el usuario.
            experience (Experience): Experiencia comparada con esos intereses.

        Returns:
            tuple[float, list[str]]: Mejor afinidad e intereses coincidentes.
        """
        category = experience.category.name if experience.category else ""
        category_normalized = cls._normalize(category)
        searchable = cls._normalize(
            " ".join((category, experience.title, experience.description or ""))
        )
        searchable_tokens = set(re.findall(r"[a-z0-9]+", searchable)) - cls._STOP_WORDS
        best_score = 0.0
        matched_interests: list[str] = []

        for interest in interests:
            if not isinstance(interest, str) or not interest.strip():
                continue
            normalized_interest = cls._normalize(interest.strip())
            interest_tokens = (
                set(re.findall(r"[a-z0-9]+", normalized_interest)) - cls._STOP_WORDS
            )
            if not interest_tokens:
                continue

            if category_normalized and (
                normalized_interest == category_normalized
                or normalized_interest in category_normalized
                or category_normalized in normalized_interest
            ):
                score = 1.0
            elif normalized_interest in searchable:
                score = 0.9
            else:
                token_coverage = len(interest_tokens & searchable_tokens) / len(
                    interest_tokens
                )
                score = 0.65 * token_coverage if token_coverage >= 0.5 else 0.0

            if score > 0:
                if score >= 0.5:
                    matched_interests.append(interest.strip())
                best_score = max(best_score, score)

        return best_score, matched_interests

    @staticmethod
    def _utc_datetime(value: datetime) -> datetime:
        """Convierte una fecha a UTC para ordenar experiencias futuras.

        Args:
            value (datetime): Fecha de la experiencia.

        Returns:
            datetime: Fecha con zona horaria UTC.
        """
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def recommend_experiences(
        self,
        user_id: str,
        latitude: float | None = None,
        longitude: float | None = None,
        radius_km: float | None = None,
        limit: int = 20,
    ) -> list[ExperienceRecommendationDTO]:
        """Ordena experiencias disponibles según intereses, ubicación y fecha.

        Args:
            user_id (str): Identificador del usuario cuyos intereses se consultan.
            latitude (float | None): Latitud opcional para calcular distancia.
            longitude (float | None): Longitud opcional para calcular distancia.
            radius_km (float | None): Radio máximo opcional; no hay uno por defecto.
            limit (int): Número máximo de recomendaciones, entre 1 y 50.

        Returns:
            list[ExperienceRecommendationDTO]: Experiencias recomendadas sin reservar cupos.

        Raises:
            HTTPException: Si los parámetros geográficos o el límite son inválidos,
            o si el usuario no existe.
        """
        location_supplied = latitude is not None or longitude is not None
        if location_supplied and (
            latitude is None
            or longitude is None
            or not -90.0 <= latitude <= 90.0
            or not -180.0 <= longitude <= 180.0
        ):
            raise HTTPException(
                status_code=422,
                detail="latitude y longitude deben ser coordenadas válidas y enviarse juntas.",
            )
        if radius_km is not None and (latitude is None or longitude is None):
            raise HTTPException(
                status_code=422,
                detail="radius_km requiere latitude y longitude; no se aplica un radio predeterminado.",
            )
        if radius_km is not None and (not isfinite(radius_km) or radius_km <= 0):
            raise HTTPException(
                status_code=422,
                detail="radius_km debe ser un número positivo y finito.",
            )
        if not 1 <= limit <= 50:
            raise HTTPException(
                status_code=422,
                detail="limit debe estar entre 1 y 50.",
            )

        user = self.user_repo.get_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
            )

        now = datetime.now(UTC)
        candidates = self.experience_repo.get_recommendation_candidates(as_of=now)
        interests = user.interests if isinstance(user.interests, list) else []
        ranked: list[
            tuple[tuple[float, bool, float, datetime, str], ExperienceRecommendationDTO]
        ] = []

        for experience in candidates:
            venue = experience.venue
            distance_km = None
            if (
                latitude is not None
                and longitude is not None
                and venue is not None
                and venue.latitude is not None
                and venue.longitude is not None
            ):
                distance_km = ExperienceMapper.calculate_haversine_km(
                    latitude,
                    longitude,
                    venue.latitude,
                    venue.longitude,
                )

            is_virtual = (
                getattr(experience.modality, "value", experience.modality) == "VIRTUAL"
            )
            if (
                radius_km is not None
                and not is_virtual
                and (distance_km is None or distance_km > radius_km)
            ):
                continue

            interest_score, matched_interests = self._interest_affinity(
                interests, experience
            )
            reasons = [
                f"Coincide con tu interés: {interest}" for interest in matched_interests
            ]
            if distance_km is not None:
                reasons.append(f"A {distance_km:.1f} km del punto que compartiste")
            if not reasons:
                reasons.append("Experiencia futura con cupos disponibles")

            event_date = self._utc_datetime(experience.event_date)
            recommendation = MatchingMapper.to_recommendation_dto(
                experience=experience,
                event_date=event_date,
                interest_score=interest_score,
                matched_interests=matched_interests,
                reasons=reasons,
                distance_km=distance_km,
            )
            sort_key = (
                -interest_score,
                distance_km is None,
                distance_km if distance_km is not None else inf,
                event_date,
                experience.id,
            )
            ranked.append((sort_key, recommendation))

        ranked.sort(key=lambda item: item[0])
        return [recommendation for _, recommendation in ranked[:limit]]
