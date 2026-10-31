from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from app.booking.entity.booking import Booking, BookingStatusEnum
from app.booking.entity.payment import Payment, PaymentStatusEnum
from app.experience.entity.category import Category
from app.experience.entity.experience import (
    Experience,
    ExperienceStatusEnum,
    ModalityEnum,
)
from app.experience.entity.venue import Venue
from app.matching.entity.search_log import SearchLog


class SearchLogRepository:
    """Persistencia de eventos de búsqueda sin conservar el texto consultado."""

    def __init__(self, db: Session) -> None:
        """Inicializa el repositorio con una sesión de base de datos.

        Args:
            db (Session): Sesión SQLAlchemy compartida con la petición.
        """
        self.db = db

    def record_unmet_search(
        self, category: str, zone: str, query_text: str | None = None, dedupe_key: str | None = None
    ) -> None:
        """Prepara una búsqueda vacía verificada sin confirmar la transacción.

        Args:
            category (str): Categoría buscada.
            zone (str): Zona consultada.
            query_text (str | None): Texto original consultado opcional.
            dedupe_key (str | None): Clave de deduplicación efímera.
        """
        search = SearchLog(
            query_text=query_text,
            category=category,
            zone=zone,
            found_results=False,
            dedupe_key=dedupe_key,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        self.db.add(search)

    def log_search(self, search: SearchLog) -> SearchLog:
        """Persiste un registro de búsqueda recibido por esta capa.

        Args:
            search (SearchLog): Registro ORM que se va a guardar.

        Returns:
            SearchLog: Registro actualizado después del commit.
        """
        self.db.add(search)
        self.db.commit()
        self.db.refresh(search)
        return search

    def get_unanswered_searches(self) -> list[SearchLog]:
        """Recupera búsquedas registradas sin resultados.

        Returns:
            list[SearchLog]: Registros cuya marca found_results es falsa.
        """
        return self.db.query(SearchLog).filter(SearchLog.found_results.is_(False)).all()


class DemandRepository:
    """Agregación de señales reales de demanda y resultados históricos de pago."""

    _MAX_TRAINING_ROWS = 50_000
    _LEGACY_DEMO_SEARCH_IDS = tuple(
        str(uuid5(NAMESPACE_URL, f"sw1-exp:hu11-demo-search:{index}"))
        for index in range(24)
    )

    def __init__(self, db: Session) -> None:
        """Inicializa la agregación de demanda y el registro de búsquedas.

        Args:
            db (Session): Sesión SQLAlchemy compartida con la petición.
        """
        self.db = db
        self.search_log_repo = SearchLogRepository(db)

    def record_unmet_search(
        self, category: str, zone: str, query_text: str | None = None, dedupe_key: str | None = None
    ) -> None:
        """Prepara una búsqueda vacía verificada sin confirmar la transacción.

        Args:
            category (str): Categoría buscada.
            zone (str): Zona consultada.
            query_text (str | None): Texto original consultado opcional.
            dedupe_key (str | None): Clave de deduplicación efímera.
        """
        self.search_log_repo.record_unmet_search(
            category=category, zone=zone, query_text=query_text, dedupe_key=dedupe_key
        )

    def get_unmet_search_counts(
        self,
        zone: str | None,
        since: datetime,
    ) -> list[tuple[str, int]]:
        """Cuenta búsquedas sin resultados por categoría y zona desde una fecha.

        Args:
            zone (str | None): Zona consultada o None para todas las zonas.
            since (datetime): Límite inferior de la ventana temporal.

        Returns:
            list[tuple[str, int]]: Categorías y cantidades ordenadas por demanda.
        """
        query = (
            self.db.query(
                SearchLog.category, func.count(SearchLog.id).label("search_count")
            )
            .filter(
                SearchLog.found_results.is_(False),
                SearchLog.category.isnot(None),
                SearchLog.created_at >= since,
                SearchLog.id.notin_(self._LEGACY_DEMO_SEARCH_IDS),
            )
        )
        if zone and zone.strip() and zone.strip().casefold() not in {"todas las zonas", "all"}:
            query = query.filter(SearchLog.zone == zone.strip())

        rows = (
            query.group_by(SearchLog.category)
            .order_by(func.count(SearchLog.id).desc(), SearchLog.category.asc())
            .all()
        )
        return [(category, int(count)) for category, count in rows]

    def get_quorum_outcome_examples(
        self,
        since: datetime,
        as_of: datetime,
    ) -> list[tuple[str, str, ModalityEnum, float, str, datetime, int, int, int]]:
        """Recupera experiencias históricas con resultados de pagos verificables.

        Args:
            since (datetime): Inicio de la ventana de entrenamiento.
            as_of (datetime): Corte temporal superior de la consulta.

        Returns:
            list[tuple[str, str, ModalityEnum, float, str, datetime, int, int, int]]:
            Zona, categoría, modalidad, precio, moneda, fecha, capacidades y
            cupos pagados de cada experiencia elegible.
        """
        currency_counts = (
            self.db.query(
                Booking.experience_id.label("experience_id"),
                func.count(func.distinct(Payment.currency)).label("currency_count"),
            )
            .join(Payment, Payment.booking_id == Booking.id)
            .filter(Payment.currency.isnot(None))
            .group_by(Booking.experience_id)
            .subquery()
        )
        paid_before_start = func.coalesce(
            func.sum(
                case(
                    (
                        and_(
                            Booking.status == BookingStatusEnum.PAID,
                            Payment.status == PaymentStatusEnum.SUCCEEDED,
                            Payment.paid_at.isnot(None),
                            Payment.paid_at <= Experience.event_date,
                        ),
                        Booking.quantity,
                    ),
                    else_=0,
                )
            ),
            0,
        )
        rows = (
            self.db.query(
                Experience.id,
                Venue.zone,
                Category.name,
                Experience.modality,
                Experience.price,
                Payment.currency,
                Experience.event_date,
                Experience.min_capacity,
                Experience.max_capacity,
                paid_before_start.label("paid_seats"),
            )
            .join(Category, Category.id == Experience.category_id)
            .join(Venue, Venue.id == Experience.venue_id)
            .join(currency_counts, currency_counts.c.experience_id == Experience.id)
            .outerjoin(Booking, Booking.experience_id == Experience.id)
            .outerjoin(Payment, Payment.booking_id == Booking.id)
            .filter(
                Experience.event_date >= since,
                Experience.event_date <= as_of,
                Payment.status.in_(
                    [PaymentStatusEnum.SUCCEEDED, PaymentStatusEnum.FAILED]
                ),
                Payment.currency.isnot(None),
                currency_counts.c.currency_count == 1,
                ~Experience.title.startswith("DEMO SINTÉTICO HU-11"),
                Experience.status.in_(
                    [
                        ExperienceStatusEnum.OPEN,
                        ExperienceStatusEnum.CONFIRMED,
                        ExperienceStatusEnum.LIVE,
                        ExperienceStatusEnum.FINISHED,
                    ]
                ),
            )
            .group_by(
                Experience.id,
                Venue.zone,
                Category.name,
                Experience.modality,
                Experience.price,
                Payment.currency,
                Experience.event_date,
                Experience.min_capacity,
                Experience.max_capacity,
            )
            .order_by(Experience.event_date.desc(), Experience.id.asc())
            .limit(self._MAX_TRAINING_ROWS)
            .all()
        )
        rows.reverse()
        currencies_by_experience: dict[str, set[str]] = {}
        for experience_id, _, _, _, _, currency, _, _, _, _ in rows:
            currencies_by_experience.setdefault(str(experience_id), set()).add(
                str(currency).upper()
            )

        return [
            (
                zone or "",
                category,
                modality,
                float(price),
                str(currency).upper(),
                event_date,
                int(min_capacity),
                int(max_capacity),
                int(paid_seats or 0),
            )
            for (
                experience_id,
                zone,
                category,
                modality,
                price,
                currency,
                event_date,
                min_capacity,
                max_capacity,
                paid_seats,
            ) in rows
            if len(currencies_by_experience[str(experience_id)]) == 1
        ]
