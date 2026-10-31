from datetime import UTC, datetime

from sqlalchemy import func, update
from sqlalchemy.orm import Session, joinedload

from app.auth.entity.user import User
from app.booking.entity.booking import Booking, BookingStatusEnum
from app.booking.entity.payment import Payment, PaymentStatusEnum
from app.experience.entity.experience import Experience
from app.matching.entity.matching_group import MatchingGroup, MatchingGroupStatusEnum
from app.matching.entity.matching_member import MatchingMember


class MatchingRepository:
    def __init__(self, db: Session):
        """Inicializa el repositorio con una sesión de base de datos.

        Args:
            db (Session): Sesión SQLAlchemy compartida con la petición.
        """
        self.db = db

    def get_experience_for_quorum(self, experience_id: str) -> Experience | None:
        """Carga y bloquea una experiencia para serializar evaluaciones de quórum.

        Args:
            experience_id (str): Identificador de la experiencia.

        Returns:
            Experience | None: Experiencia bloqueada o None si no existe.
        """
        return (
            self.db.query(Experience)
            .filter(Experience.id == str(experience_id))
            .with_for_update()
            .first()
        )

    def count_paid_seats(self, experience_id: str) -> int:
        """Cuenta cupos con reserva pagada y pago exitoso persistido.

        Args:
            experience_id (str): Identificador de la experiencia.

        Returns:
            int: Suma de cupos pagados y liquidados hasta el momento.
        """
        paid_at_cutoff = datetime.now(UTC).replace(tzinfo=None)
        paid_seats = (
            self.db.query(func.coalesce(func.sum(Booking.quantity), 0))
            .join(Payment, Payment.booking_id == Booking.id)
            .filter(
                Booking.experience_id == str(experience_id),
                Booking.status == BookingStatusEnum.PAID,
                Payment.status == PaymentStatusEnum.SUCCEEDED,
                Payment.paid_at.isnot(None),
                Payment.paid_at <= paid_at_cutoff,
            )
            .scalar()
        )
        return int(paid_seats or 0)

    def get_experience_for_matching(self, experience_id: str) -> Experience | None:
        """Carga y bloquea una experiencia para serializar postulaciones.

        Args:
            experience_id (str): Identificador de la experiencia.

        Returns:
            Experience | None: Experiencia bloqueada o None si no existe.
        """
        return (
            self.db.query(Experience)
            .filter(Experience.id == str(experience_id))
            .with_for_update()
            .first()
        )

    def get_by_id(self, group_id: str) -> MatchingGroup | None:
        """Busca un grupo por identificador.

        Args:
            group_id (str): Identificador del grupo.

        Returns:
            MatchingGroup | None: Grupo encontrado o None.
        """
        return (
            self.db.query(MatchingGroup)
            .filter(MatchingGroup.id == str(group_id))
            .first()
        )

    def get_groups_by_experience(self, experience_id: str) -> list[MatchingGroup]:
        """Lista los grupos de una experiencia en orden de creación.

        Args:
            experience_id (str): Identificador de la experiencia.

        Returns:
            list[MatchingGroup]: Grupos asociados, posiblemente vacíos.
        """
        return (
            self.db.query(MatchingGroup)
            .filter(MatchingGroup.experience_id == str(experience_id))
            .order_by(MatchingGroup.created_at.asc(), MatchingGroup.id.asc())
            .all()
        )

    def list_by_experience(self, experience_id: str) -> list[MatchingGroup]:
        """Alias compatible para listar grupos de una experiencia."""
        return self.get_groups_by_experience(experience_id)

    def get_member_group(
        self, experience_id: str, user_id: str
    ) -> MatchingGroup | None:
        """Busca el grupo donde se postuló un usuario para una experiencia.

        Args:
            experience_id (str): Identificador de la experiencia.
            user_id (str): Identificador del usuario.

        Returns:
            MatchingGroup | None: Grupo de la postulación o None.
        """
        return (
            self.db.query(MatchingGroup)
            .join(MatchingMember, MatchingMember.matching_group_id == MatchingGroup.id)
            .filter(
                MatchingGroup.experience_id == str(experience_id),
                MatchingMember.user_id == str(user_id),
            )
            .first()
        )

    def count_members(self, group_id: str) -> int:
        """Cuenta postulaciones existentes en un grupo, no reservas pagadas.

        Args:
            group_id (str): Identificador del grupo.

        Returns:
            int: Número de usuarios postulados.
        """
        count = (
            self.db.query(func.count(MatchingMember.id))
            .filter(MatchingMember.matching_group_id == str(group_id))
            .scalar()
        )
        return int(count or 0)

    def get_group_member_counts(self, experience_id: str) -> dict[str, int]:
        """Cuenta postulaciones de todos los grupos de una experiencia en una consulta.

        Args:
            experience_id (str): Identificador de la experiencia.

        Returns:
            dict[str, int]: Cantidad de postulados por identificador de grupo.
        """
        rows = (
            self.db.query(MatchingGroup.id, func.count(MatchingMember.id))
            .outerjoin(
                MatchingMember, MatchingMember.matching_group_id == MatchingGroup.id
            )
            .filter(MatchingGroup.experience_id == str(experience_id))
            .group_by(MatchingGroup.id)
            .all()
        )
        return {group_id: int(count) for group_id, count in rows}

    def get_group_member_interests(
        self, group_ids: list[str]
    ) -> dict[str, list[list[str]]]:
        """Carga intereses de miembros de varios grupos en una sola consulta.

        Args:
            group_ids (list[str]): Identificadores de los grupos candidatos.

        Returns:
            dict[str, list[list[str]]]: Listas de intereses por grupo y miembro.
        """
        if not group_ids:
            return {}

        rows = (
            self.db.query(MatchingMember.matching_group_id, User.interests)
            .join(User, User.id == MatchingMember.user_id)
            .filter(
                MatchingMember.matching_group_id.in_(
                    [str(group_id) for group_id in group_ids]
                )
            )
            .order_by(
                MatchingMember.matching_group_id,
                MatchingMember.joined_at,
                MatchingMember.id,
            )
            .all()
        )
        group_interests: dict[str, list[list[str]]] = {}
        for group_id, interests in rows:
            group_interests.setdefault(group_id, []).append(
                interests if isinstance(interests, list) else []
            )
        return group_interests

    def create_group(self, group: MatchingGroup) -> MatchingGroup:
        """Agrega un grupo a la sesión y ejecuta flush sin confirmar la transacción.

        Args:
            group (MatchingGroup): Grupo que se va a crear.

        Returns:
            MatchingGroup: Entidad con los valores generados por flush.
        """
        self.db.add(group)
        self.db.flush()
        return group

    def add_member(self, member: MatchingMember) -> MatchingMember:
        """Agrega una postulación y actualiza el contador del grupo sin commit.

        Args:
            member (MatchingMember): Postulación que se va a crear.

        Returns:
            MatchingMember: Miembro agregado a la sesión.
        """
        self.db.add(member)
        self.db.flush()
        if member.matching_group is not None:
            member.matching_group.current_members = self.count_members(
                member.matching_group_id
            )
        return member

    def get_members(self, group_id: str) -> list[MatchingMember]:
        """Lista miembros de un grupo junto con sus usuarios.

        Args:
            group_id (str): Identificador del grupo.

        Returns:
            list[MatchingMember]: Miembros ordenados por fecha de ingreso.
        """
        return (
            self.db.query(MatchingMember)
            .options(joinedload(MatchingMember.user))
            .filter(MatchingMember.matching_group_id == str(group_id))
            .order_by(MatchingMember.joined_at.asc(), MatchingMember.id.asc())
            .all()
        )

    def update_status(
        self, group_id: str, status: MatchingGroupStatusEnum
    ) -> MatchingGroup | None:
        """Actualiza el estado de un grupo sin confirmar la transacción.

        Args:
            group_id (str): Identificador del grupo.
            status (MatchingGroupStatusEnum): Nuevo estado solicitado.

        Returns:
            MatchingGroup | None: Grupo actualizado o None si no existe.
        """
        group = self.get_by_id(group_id)
        if group is None:
            return None
        group.status = status
        self.db.flush()
        return group

    def mark_experience_groups_reached(self, experience_id: str) -> None:
        """Marca como alcanzados los grupos abiertos de una experiencia.

        Args:
            experience_id (str): Identificador de la experiencia confirmada.
        """
        self.db.execute(
            update(MatchingGroup)
            .where(
                MatchingGroup.experience_id == str(experience_id),
                MatchingGroup.status == MatchingGroupStatusEnum.OPEN,
            )
            .values(status=MatchingGroupStatusEnum.REACHED)
        )
