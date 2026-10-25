from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import cos, log1p, pi, sin
from statistics import median
from threading import Lock
from typing import Any, ClassVar
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from app.auth.repository.user_repository import UserRepository
from app.experience.entity.experience import ModalityEnum
from app.experience.repository.venue_repository import VenueRepository
from app.matching.dto.matching_dto import (
    DemandModelStatusDTO,
    SearchLogDTO,
    SuggestedExperienceDTO,
    UnmetDemandInsightDTO,
)
from app.matching.repository.demand_repository import (
    DemandRepository,
    SearchLogRepository,
)


@dataclass(frozen=True)
class _DemandModelSnapshot:
    model: Any | None
    model_status: str
    model_version: str | None
    training_example_count: int
    positive_example_count: int
    negative_example_count: int
    model_currency: str | None
    validation_example_count: int
    validation_auc: float | None
    validation_brier_score: float | None
    baseline_brier_score: float | None
    evaluated_at: datetime
    message: str


class DemandPredictionService:
    """Combina demanda observada con referencias históricas de experiencias viables."""

    _MIN_SUCCESSFUL_EXAMPLES = 5
    _MIN_OUTCOME_EXAMPLES = 10
    _MIN_EXAMPLES_PER_OUTCOME = 2
    _MIN_MODEL_EXAMPLES = 200
    _MIN_MODEL_EXAMPLES_PER_CLASS = 30
    _MIN_VALIDATION_EXAMPLES_PER_CLASS = 10
    _VALIDATION_FRACTION = 0.2
    _VALIDATION_AUC_FLOOR = 0.60
    _TRAINING_WINDOW_DAYS = 730
    _MODEL_VERSION = "demand-quorum-logistic-v1"
    _MODEL_LOCK: ClassVar[Lock] = Lock()
    _MODEL_CACHE_SIGNATURE: ClassVar[int | None] = None
    _MODEL_CACHE: ClassVar[_DemandModelSnapshot | None] = None
    _LOCAL_TIMEZONE = ZoneInfo("America/La_Paz")
    _WEEKDAYS = (
        "lunes",
        "martes",
        "miércoles",
        "jueves",
        "viernes",
        "sábado",
        "domingo",
    )
    _TIME_PERIODS = ("madrugada", "mañana", "tarde", "noche")

    def __init__(self, db: Session) -> None:
        """Inicializa repositorios de demanda, usuarios y establecimientos.

        Args:
            db (Session): Sesión SQLAlchemy de la petición.
        """
        self.db = db
        self.demand_repo = DemandRepository(db)
        self.user_repo = UserRepository(db)
        self.venue_repo = VenueRepository(db)

    def record_unmet_search(self, dto: SearchLogDTO) -> None:
        """Confirma una búsqueda vacía verificada sin conservar texto libre.

        Args:
            dto (SearchLogDTO): Señal clasificada por el catálogo; se ignoran
            búsquedas con resultados o sin categoría y zona.
        """
        if dto.found_results or not dto.category or not dto.zone:
            return
        try:
            self.demand_repo.record_unmet_search(
                category=dto.category.strip(),
                zone=dto.zone.strip(),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    @staticmethod
    def _aggregate_id(zone: str, category: str) -> str:
        """Crea una identidad reproducible para un agregado no materializado.

        Args:
            zone (str): Zona consultada.
            category (str): Categoría de la búsqueda.

        Returns:
            str: UUID estable para la combinación normalizada.
        """
        key = f"{zone.strip().casefold()}:{category.strip().casefold()}"
        return str(uuid5(NAMESPACE_URL, f"sw1-exp:unmet-demand:{key}"))

    def _authorize_zone_access(
        self, user_id: str, zone: str, allow_host: bool = False
    ) -> str:
        """Autoriza el acceso a datos de una zona y devuelve su nombre canónico.

        Args:
            user_id (str): Usuario que solicita el acceso.
            zone (str): Zona consultada.
            allow_host (bool): Permite también anfitriones en zonas existentes.

        Returns:
            str: Nombre canónico de la zona autorizada.

        Raises:
            HTTPException: Si la zona está vacía o el usuario carece de acceso.
        """
        normalized_zone = zone.strip()
        if not normalized_zone:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="La zona es obligatoria.",
            )

        roles = {role.upper() for role in self.user_repo.get_user_roles(user_id)}
        if "ADMIN" in roles:
            return (
                self.venue_repo.get_canonical_zone(normalized_zone) or normalized_zone
            )
        canonical_zone = self.venue_repo.get_canonical_zone(normalized_zone)
        if "VENUE" in roles and self.venue_repo.owns_venue_in_zone(
            user_id, normalized_zone
        ):
            return canonical_zone or normalized_zone
        if allow_host and "HOST" in roles and canonical_zone is not None:
            return canonical_zone

        if allow_host:
            detail = "Se requiere rol HOST, administrador o propiedad de un establecimiento en esa zona."
        else:
            detail = "Solo un administrador o propietario de un establecimiento en esa zona puede consultar estos datos."
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    @staticmethod
    def _validate_window(window_days: int) -> None:
        """Valida el rango permitido para una ventana de análisis.

        Args:
            window_days (int): Número de días retrospectivos solicitado.

        Raises:
            HTTPException: Si la ventana no está entre 1 y 365 días.
        """
        if not 1 <= window_days <= 365:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="window_days debe estar entre 1 y 365.",
            )

    def _get_counts(
        self, zone: str, window_days: int
    ) -> tuple[list[tuple[str, int]], datetime]:
        """Consulta conteos de búsquedas vacías y fija la hora del análisis.

        Args:
            zone (str): Zona ya autorizada y normalizada.
            window_days (int): Número de días retrospectivos.

        Returns:
            tuple[list[tuple[str, int]], datetime]: Conteos por categoría
            y fecha UTC en que se generó el agregado.

        Raises:
            HTTPException: Si la ventana no está entre 1 y 365 días.
        """
        self._validate_window(window_days)
        analyzed_at = datetime.now(UTC)
        since = (analyzed_at - timedelta(days=window_days)).replace(tzinfo=None)
        return self.demand_repo.get_unmet_search_counts(
            zone=zone, since=since
        ), analyzed_at

    def get_zone_insights(
        self,
        user_id: str,
        zone: str,
        window_days: int = 30,
    ) -> list[UnmetDemandInsightDTO]:
        """Agrupa las búsquedas verificadas sin resultados en una zona autorizada.

        Args:
            user_id (str): Usuario que consulta la demanda de la zona.
            zone (str): Zona del establecimiento consultado.
            window_days (int): Días retrospectivos del agregado, entre 1 y 365.

        Returns:
            list[UnmetDemandInsightDTO]: Conteos de búsquedas por categoría;
            no representan personas únicas ni incluyen precio estimado.

        Raises:
            HTTPException: Si la zona, la ventana o el acceso son inválidos.
        """
        authorized_zone = self._authorize_zone_access(user_id, zone)
        counts, analyzed_at = self._get_counts(authorized_zone, window_days)
        return [
            UnmetDemandInsightDTO(
                id=self._aggregate_id(authorized_zone, category),
                zone=authorized_zone,
                category_keyword=category,
                search_count=count,
                suggested_price=None,
                suggested_time_slot=None,
                window_days=window_days,
                analyzed_at=analyzed_at,
            )
            for category, count in counts
        ]

    @classmethod
    def _feature_record(
        cls,
        zone: str,
        category: str,
        modality: ModalityEnum | str,
        price: float,
        min_capacity: int,
        max_capacity: int,
        weekday_hour: tuple[int, int],
    ) -> dict[str, float | str]:
        """Codifica atributos de una experiencia para el clasificador.

        Args:
            zone (str): Zona de la experiencia.
            category (str): Categoría temática.
            modality (ModalityEnum | str): Modalidad publicada.
            price (float): Precio observado en la moneda del modelo.
            min_capacity (int): Mínimo de cupos para alcanzar quórum.
            max_capacity (int): Capacidad máxima publicada.
            weekday_hour (tuple[int, int]): Día de semana y hora local.

        Returns:
            dict[str, float | str]: Variables categóricas y numéricas del modelo.
        """
        weekday, hour = weekday_hour
        max_capacity = max(1, max_capacity)
        return {
            "category": category.strip().casefold() or "unknown",
            "zone": zone.strip().casefold() or "unknown",
            "modality": getattr(modality, "value", str(modality)).upper(),
            "log_price": log1p(max(0.0, float(price))),
            "min_capacity": float(min_capacity),
            "log_max_capacity": log1p(float(max_capacity)),
            "capacity_ratio": min_capacity / max_capacity,
            "weekday_sin": sin(2.0 * pi * weekday / 7.0),
            "weekday_cos": cos(2.0 * pi * weekday / 7.0),
            "hour_sin": sin(2.0 * pi * hour / 24.0),
            "hour_cos": cos(2.0 * pi * hour / 24.0),
        }

    @classmethod
    def _outcome_features(
        cls,
        example: tuple[str, str, ModalityEnum, float, str, datetime, int, int, int],
    ) -> dict[str, float | str]:
        """Extrae atributos predictivos de un resultado histórico pagado.

        Args:
            example (tuple[str, str, ModalityEnum, float, str, datetime, int, int, int]):
                Zona, categoría, modalidad, precio, moneda, fecha, capacidades y cupos pagados.

        Returns:
            dict[str, float | str]: Variables del evento con horario local codificado.
        """
        (
            zone,
            category,
            modality,
            price,
            _,
            event_date,
            min_capacity,
            max_capacity,
            _,
        ) = example
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=UTC)
        local_event_date = event_date.astimezone(cls._LOCAL_TIMEZONE)
        return cls._feature_record(
            zone,
            category,
            modality,
            price,
            min_capacity,
            max_capacity,
            (local_event_date.weekday(), local_event_date.hour),
        )

    @classmethod
    def _fit_demand_model(
        cls,
        examples: list[
            tuple[str, str, ModalityEnum, float, str, datetime, int, int, int]
        ],
    ) -> _DemandModelSnapshot:
        """Entrena el clasificador solo si hay datos y validación temporal suficientes.

        Args:
            examples (list[tuple]): Resultados históricos pagados ordenados por fecha.

        Returns:
            _DemandModelSnapshot: Modelo aprobado o estado explícito de insuficiencia
            de datos, dependencias o calidad de validación.
        """
        evaluated_at = datetime.now(UTC)
        currency_counts = Counter(example[4] for example in examples)
        model_currency = (
            min(
                currency_counts,
                key=lambda currency: (-currency_counts[currency], currency),
            )
            if currency_counts
            else None
        )
        examples = [example for example in examples if example[4] == model_currency]
        labels = [int(example[8] >= example[6]) for example in examples]
        positive_count = sum(labels)
        negative_count = len(labels) - positive_count
        sample_count = len(examples)

        def snapshot(
            model_status: str,
            model: Any | None,
            message: str,
            validation_count: int = 0,
            auc: float | None = None,
            brier: float | None = None,
            baseline_brier: float | None = None,
            version: str | None = None,
        ) -> _DemandModelSnapshot:
            return _DemandModelSnapshot(
                model=model,
                model_status=model_status,
                model_version=version,
                training_example_count=sample_count,
                positive_example_count=positive_count,
                negative_example_count=negative_count,
                model_currency=model_currency,
                validation_example_count=validation_count,
                validation_auc=round(float(auc), 4) if auc is not None else None,
                validation_brier_score=round(float(brier), 4)
                if brier is not None
                else None,
                baseline_brier_score=(
                    round(float(baseline_brier), 4)
                    if baseline_brier is not None
                    else None
                ),
                evaluated_at=evaluated_at,
                message=message,
            )

        if (
            sample_count < cls._MIN_MODEL_EXAMPLES
            or min(positive_count, negative_count) < cls._MIN_MODEL_EXAMPLES_PER_CLASS
        ):
            return snapshot(
                "INSUFFICIENT_DATA",
                None,
                (
                    f"Se requieren al menos {cls._MIN_MODEL_EXAMPLES} eventos reales y "
                    f"{cls._MIN_MODEL_EXAMPLES_PER_CLASS} ejemplos de cada desenlace; "
                    f"hay {sample_count} ({positive_count} positivos, {negative_count} negativos)."
                ),
            )

        try:
            from sklearn.feature_extraction import DictVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.metrics import brier_score_loss, roc_auc_score
            from sklearn.pipeline import make_pipeline
            from sklearn.preprocessing import StandardScaler
        except (ImportError, OSError) as exc:
            return snapshot(
                "INSUFFICIENT_DATA",
                None,
                f"Entorno sin librerías de entrenamiento disponibles ({exc}).",
            )

        split_index = int(sample_count * (1.0 - cls._VALIDATION_FRACTION))
        train_examples, validation_examples = (
            examples[:split_index],
            examples[split_index:],
        )
        train_labels, validation_labels = labels[:split_index], labels[split_index:]
        train_positive = sum(train_labels)
        train_negative = len(train_labels) - train_positive
        if min(train_positive, train_negative) < cls._MIN_MODEL_EXAMPLES_PER_CLASS:
            return snapshot(
                "INSUFFICIENT_DATA",
                None,
                "La partición de entrenamiento no conserva suficientes ejemplos de ambas clases.",
                validation_count=len(validation_examples),
            )

        validation_positive = sum(validation_labels)
        validation_negative = len(validation_labels) - validation_positive
        if (
            min(validation_positive, validation_negative)
            < cls._MIN_VALIDATION_EXAMPLES_PER_CLASS
        ):
            return snapshot(
                "INSUFFICIENT_DATA",
                None,
                "El holdout temporal no contiene suficientes casos positivos y negativos para validarlo.",
                validation_count=len(validation_examples),
            )

        def pipeline() -> Any:
            return make_pipeline(
                DictVectorizer(sparse=True),
                StandardScaler(with_mean=False),
                LogisticRegression(
                    C=0.5,
                    max_iter=1000,
                    solver="lbfgs",
                    random_state=17,
                ),
            )

        validation_model = pipeline()
        validation_model.fit(
            [cls._outcome_features(example) for example in train_examples],
            train_labels,
        )
        validation_probabilities = validation_model.predict_proba(
            [cls._outcome_features(example) for example in validation_examples]
        )[:, 1]
        auc = float(roc_auc_score(validation_labels, validation_probabilities))
        brier = float(brier_score_loss(validation_labels, validation_probabilities))
        train_base_rate = sum(train_labels) / len(train_labels)
        baseline_brier = float(
            brier_score_loss(
                validation_labels, [train_base_rate] * len(validation_labels)
            )
        )
        if auc < cls._VALIDATION_AUC_FLOOR or brier >= baseline_brier:
            return snapshot(
                "VALIDATION_FAILED",
                None,
                (
                    "El modelo no superó el umbral de validación temporal "
                    f"(AUC mínimo {cls._VALIDATION_AUC_FLOOR:.2f} y Brier mejor que el baseline)."
                ),
                validation_count=len(validation_examples),
                auc=auc,
                brier=brier,
                baseline_brier=baseline_brier,
                version=cls._MODEL_VERSION,
            )

        final_model = pipeline()
        final_model.fit(
            [cls._outcome_features(example) for example in examples],
            labels,
        )
        return snapshot(
            "TRAINED",
            final_model,
            f"Modelo aprobado para {model_currency}: supera la validación temporal y mejora el baseline de prevalencia.",
            validation_count=len(validation_examples),
            auc=auc,
            brier=brier,
            baseline_brier=baseline_brier,
            version=cls._MODEL_VERSION,
        )

    @classmethod
    def _get_demand_model(
        cls,
        examples: list[
            tuple[str, str, ModalityEnum, float, str, datetime, int, int, int]
        ],
        force_retrain: bool = False,
    ) -> _DemandModelSnapshot:
        """Reutiliza el modelo en memoria si el historial no cambió.

        Args:
            examples (list[tuple]): Resultados históricos usados como entrada.
            force_retrain (bool): Obliga a recalcular aunque la firma coincida.

        Returns:
            _DemandModelSnapshot: Modelo almacenado en caché o recién entrenado.
        """
        signature = hash(tuple(examples))
        with cls._MODEL_LOCK:
            if (
                not force_retrain
                and cls._MODEL_CACHE is not None
                and cls._MODEL_CACHE_SIGNATURE == signature
            ):
                return cls._MODEL_CACHE
            cls._MODEL_CACHE = cls._fit_demand_model(examples)
            cls._MODEL_CACHE_SIGNATURE = signature
            return cls._MODEL_CACHE

    @staticmethod
    def _model_status_dto(snapshot: _DemandModelSnapshot) -> DemandModelStatusDTO:
        """Convierte el resultado interno de entrenamiento en un DTO auditable.

        Args:
            snapshot (_DemandModelSnapshot): Estado y métricas calculadas.

        Returns:
            DemandModelStatusDTO: Estado público del modelo de quórum.
        """
        return DemandModelStatusDTO(
            model_status=snapshot.model_status,
            model_version=snapshot.model_version,
            training_window_days=DemandPredictionService._TRAINING_WINDOW_DAYS,
            training_example_count=snapshot.training_example_count,
            positive_example_count=snapshot.positive_example_count,
            negative_example_count=snapshot.negative_example_count,
            model_currency=snapshot.model_currency,
            validation_example_count=snapshot.validation_example_count,
            validation_auc=snapshot.validation_auc,
            validation_brier_score=snapshot.validation_brier_score,
            baseline_brier_score=snapshot.baseline_brier_score,
            evaluated_at=snapshot.evaluated_at,
            message=snapshot.message,
        )

    def train_quorum_model(self, user_id: str) -> DemandModelStatusDTO:
        """Entrena y valida el clasificador de quórum con historial real.

        Args:
            user_id (str): Identificador del administrador solicitante.

        Returns:
            DemandModelStatusDTO: Estado del modelo y métricas del holdout temporal.

        Raises:
            HTTPException: Si el usuario no tiene rol de administrador.
        """
        roles = {role.upper() for role in self.user_repo.get_user_roles(user_id)}
        if "ADMIN" not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo un administrador puede iniciar el entrenamiento del modelo.",
            )

        as_of = datetime.now(UTC).replace(tzinfo=None)
        since = as_of - timedelta(days=self._TRAINING_WINDOW_DAYS)
        examples = self.demand_repo.get_quorum_outcome_examples(
            since=since, as_of=as_of
        )
        snapshot = self._get_demand_model(examples, force_retrain=True)
        return self._model_status_dto(snapshot)

    _BETA_PRIOR_ALPHA = 2.0
    _BETA_PRIOR_BETA = 2.0
    _STRATUM_PRIOR_STRENGTH = 5.0

    @classmethod
    def _local_time_slot(cls, event_date: datetime) -> tuple[int, int]:
        """Clasifica la fecha de un evento por día y franja horaria local.

        Args:
            event_date (datetime): Fecha del evento, en UTC si no tiene zona.

        Returns:
            tuple[int, int]: Índices de día de semana y período del día.
        """
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=UTC)
        local_event_date = event_date.astimezone(cls._LOCAL_TIMEZONE)
        hour = local_event_date.hour
        period_index = 0 if hour < 5 else 1 if hour < 12 else 2 if hour < 18 else 3
        return local_event_date.weekday(), period_index

    @classmethod
    def _time_slot_label(cls, slot: tuple[int, int]) -> str:
        """Convierte una franja horaria local en una etiqueta legible.

        Args:
            slot (tuple[int, int]): Índices de día y período del día.

        Returns:
            str: Día de semana y franja horaria descriptiva.
        """
        weekday_index, period_index = slot
        return (
            f"{cls._WEEKDAYS[weekday_index]} por la {cls._TIME_PERIODS[period_index]}"
        )

    @classmethod
    def _historical_event_references(
        cls,
        examples: list[tuple[str, ModalityEnum, float, str, datetime, int, int]],
    ) -> tuple[
        float | None,
        str | None,
        str | None,
        str | None,
        tuple[int, int] | None,
        int | None,
        int | None,
        int,
    ]:
        """Deriva precio, modalidad y horario de eventos exitosos comparables.

        Args:
            examples (list[tuple]): Experiencias previas que alcanzaron quórum.

        Returns:
            tuple: Precio, moneda, franja, modalidad, día y hora, capacidades
            y cantidad de comparables; valores nulos si el historial no alcanza.
        """
        if len(examples) < cls._MIN_SUCCESSFUL_EXAMPLES:
            return None, None, None, None, None, None, None, 0

        currency_counts = Counter(example[3] for example in examples)
        recommended_currency = min(
            currency_counts, key=lambda currency: (-currency_counts[currency], currency)
        )
        currency_examples = [
            example for example in examples if example[3] == recommended_currency
        ]
        if len(currency_examples) < cls._MIN_SUCCESSFUL_EXAMPLES:
            return None, None, None, None, None, None, None, 0

        joint_counts = Counter(
            (
                getattr(example[1], "value", str(example[1])),
                cls._local_time_slot(example[4]),
            )
            for example in currency_examples
        )
        (recommended_modality, (weekday_index, period_index)), _ = min(
            joint_counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1][0], item[0][1][1]),
        )
        comparable = [
            example
            for example in currency_examples
            if getattr(example[1], "value", str(example[1])) == recommended_modality
            and cls._local_time_slot(example[4]) == (weekday_index, period_index)
        ]
        if len(comparable) < cls._MIN_SUCCESSFUL_EXAMPLES:
            return None, None, None, None, None, None, None, 0
        suggested_price = round(median(example[2] for example in comparable), 2)
        local_hours = [
            (
                example[4].replace(tzinfo=UTC)
                if example[4].tzinfo is None
                else example[4]
            )
            .astimezone(cls._LOCAL_TIMEZONE)
            .hour
            for example in comparable
        ]
        hour_counts = Counter(local_hours)
        recommended_hour = min(hour_counts, key=lambda hour: (-hour_counts[hour], hour))
        recommended_time_slot = cls._time_slot_label((weekday_index, period_index))
        assumed_min_capacity = max(
            1, round(median(example[5] for example in comparable))
        )
        assumed_max_capacity = max(
            assumed_min_capacity,
            round(median(example[6] for example in comparable)),
        )
        return (
            suggested_price,
            recommended_currency,
            recommended_time_slot,
            recommended_modality,
            (weekday_index, recommended_hour),
            assumed_min_capacity,
            assumed_max_capacity,
            len(comparable),
        )

    @classmethod
    def _estimate_quorum_probability(
        cls,
        outcomes: list[tuple[str, ModalityEnum, float, str, datetime, int, int]],
        candidate_price: float | None,
        candidate_currency: str | None,
        candidate_time_slot: str | None,
        candidate_modality: str | None,
    ) -> tuple[float | None, str]:
        """Estima quórum con baseline bayesiano cuando hay historial comparable.

        Args:
            outcomes (list[tuple]): Resultados pagados de la zona y categoría.
            candidate_price (float | None): Precio sugerido, si existe.
            candidate_currency (str | None): Moneda del precio sugerido.
            candidate_time_slot (str | None): Franja horaria sugerida.
            candidate_modality (str | None): Modalidad sugerida.

        Returns:
            tuple[float | None, str]: Probabilidad estimada y fuente, o None
            con motivo de historial insuficiente.
        """
        if candidate_currency is None:
            return None, "INSUFFICIENT_HISTORY"
        selected = [outcome for outcome in outcomes if outcome[3] == candidate_currency]
        successes = sum(
            paid_seats >= minimum for _, _, _, _, _, minimum, paid_seats in selected
        )
        failures = len(selected) - successes
        if (
            len(selected) < cls._MIN_OUTCOME_EXAMPLES
            or min(successes, failures) < cls._MIN_EXAMPLES_PER_OUTCOME
        ):
            return None, "INSUFFICIENT_HISTORY"

        base_rate = (successes + cls._BETA_PRIOR_ALPHA) / (
            len(selected) + cls._BETA_PRIOR_ALPHA + cls._BETA_PRIOR_BETA
        )
        comparable = selected
        if (
            candidate_price is not None
            and candidate_time_slot is not None
            and candidate_modality is not None
        ):
            candidate_modality_value = getattr(
                candidate_modality, "value", candidate_modality
            )
            candidate_slot = None
            for (
                _,
                historical_modality,
                historical_price,
                _,
                event_date,
                _,
                _,
            ) in selected:
                event_slot = cls._local_time_slot(event_date)
                if (
                    getattr(historical_modality, "value", str(historical_modality))
                    == candidate_modality_value
                    and abs(historical_price - candidate_price)
                    / max(candidate_price, 1.0)
                    <= 0.25
                    and cls._time_slot_label(event_slot) == candidate_time_slot
                ):
                    candidate_slot = event_slot
                    break
            if candidate_slot is not None:
                comparable = [
                    outcome
                    for outcome in selected
                    if getattr(outcome[1], "value", str(outcome[1]))
                    == candidate_modality_value
                    and abs(outcome[2] - candidate_price) / max(candidate_price, 1.0)
                    <= 0.25
                    and cls._local_time_slot(outcome[4]) == candidate_slot
                ]

        comparable_successes = sum(
            paid_seats >= minimum for _, _, _, _, _, minimum, paid_seats in comparable
        )
        probability = (
            comparable_successes + cls._STRATUM_PRIOR_STRENGTH * base_rate
        ) / (len(comparable) + cls._STRATUM_PRIOR_STRENGTH)
        return round(probability, 4), "HISTORICAL_BAYESIAN"

    def generate_experience_suggestions(
        self,
        user_id: str,
        zone: str,
        window_days: int = 30,
    ) -> list[SuggestedExperienceDTO]:
        """Propone categorías de eventos usando demanda observada e historial pagado.

        Usa una probabilidad del modelo solo si superó la validación; de otro modo
        aplica el baseline histórico cuando corresponde o devuelve una estimación nula.

        Args:
            user_id (str): Anfitrión o usuario con acceso autorizado a la zona.
            zone (str): Zona donde se podrían crear experiencias.
            window_days (int): Días retrospectivos de búsquedas, entre 1 y 365.

        Returns:
            list[SuggestedExperienceDTO]: Sugerencias ordenadas por búsquedas
            insatisfechas con referencias históricas cuando hay datos suficientes.

        Raises:
            HTTPException: Si la zona, la ventana o el acceso son inválidos.
        """
        authorized_zone = self._authorize_zone_access(user_id, zone, allow_host=True)
        counts, analyzed_at = self._get_counts(authorized_zone, window_days)
        if not counts:
            return []

        as_of = analyzed_at.replace(tzinfo=None)
        training_since = as_of - timedelta(days=self._TRAINING_WINDOW_DAYS)
        training_examples = self.demand_repo.get_quorum_outcome_examples(
            since=training_since,
            as_of=as_of,
        )
        model_snapshot = self._get_demand_model(training_examples)
        model_status = self._model_status_dto(model_snapshot)

        local_history_since = as_of - timedelta(days=365)
        zone_key = authorized_zone.casefold()
        local_outcomes_by_category: dict[
            str, list[tuple[str, ModalityEnum, float, str, datetime, int, int]]
        ] = {}
        local_successes_by_category: dict[
            str, list[tuple[str, ModalityEnum, float, str, datetime, int, int]]
        ] = {}
        category_successes: dict[
            str, list[tuple[str, ModalityEnum, float, str, datetime, int, int]]
        ] = {}

        for example in training_examples:
            (
                example_zone,
                category,
                modality,
                price,
                currency,
                event_date,
                min_capacity,
                max_capacity,
                paid_seats,
            ) = example
            category_key = category.casefold()
            reference = (
                category,
                modality,
                price,
                currency,
                event_date,
                min_capacity,
                max_capacity,
            )
            is_recent = event_date >= local_history_since
            if paid_seats >= min_capacity and is_recent:
                category_successes.setdefault(category_key, []).append(reference)
                if example_zone.casefold() == zone_key:
                    local_successes_by_category.setdefault(category_key, []).append(
                        reference
                    )

            if not is_recent or example_zone.casefold() != zone_key:
                continue
            local_outcomes_by_category.setdefault(category_key, []).append(
                (
                    category,
                    modality,
                    price,
                    currency,
                    event_date,
                    min_capacity,
                    paid_seats,
                )
            )

        suggestions: list[SuggestedExperienceDTO] = []
        for category, count in counts:
            category_key = category.casefold()
            selected_outcomes = local_outcomes_by_category.get(category_key, [])
            local_successes = local_successes_by_category.get(category_key, [])
            category_history = category_successes.get(category_key, [])
            if len(local_successes) >= self._MIN_SUCCESSFUL_EXAMPLES:
                reference_examples = local_successes
                reference_scope = "ZONE_CATEGORY"
            elif len(category_history) >= self._MIN_SUCCESSFUL_EXAMPLES:
                reference_examples = category_history
                reference_scope = "CATEGORY_CROSS_ZONE"
            else:
                reference_examples = []
                reference_scope = None

            (
                price,
                candidate_currency,
                time_slot,
                modality,
                candidate_weekday_hour,
                assumed_min_capacity,
                assumed_max_capacity,
                comparable_reference_count,
            ) = self._historical_event_references(reference_examples)
            if price is None:
                reference_scope = None
            baseline_probability, baseline_source = self._estimate_quorum_probability(
                selected_outcomes,
                price,
                candidate_currency,
                time_slot,
                modality,
            )

            model_probability = None
            if (
                model_snapshot.model_status == "TRAINED"
                and model_snapshot.model is not None
                and candidate_currency == model_snapshot.model_currency
                and price is not None
                and time_slot is not None
                and modality is not None
                and candidate_weekday_hour is not None
                and assumed_min_capacity is not None
                and assumed_max_capacity is not None
            ):
                candidate_features = self._feature_record(
                    authorized_zone,
                    category,
                    modality,
                    price,
                    assumed_min_capacity,
                    assumed_max_capacity,
                    candidate_weekday_hour,
                )
                model_probability = float(
                    model_snapshot.model.predict_proba([candidate_features])[0][1]
                )

            if model_probability is not None:
                quorum_probability = round(model_probability, 4)
                recommendation_source = "TRAINED_LOGISTIC_REGRESSION"
            else:
                quorum_probability = baseline_probability
                recommendation_source = baseline_source
                if (
                    baseline_source == "INSUFFICIENT_HISTORY"
                    and model_snapshot.model_status == "VALIDATION_FAILED"
                ):
                    recommendation_source = "MODEL_VALIDATION_FAILED"

            suggestions.append(
                SuggestedExperienceDTO(
                    zone=authorized_zone,
                    category_keyword=category,
                    estimated_interest_count=None,
                    suggested_price=price,
                    suggested_currency=candidate_currency,
                    recommended_time_slot=time_slot,
                    recommended_modality=modality,
                    historical_quorum_example_count=comparable_reference_count,
                    historical_outcome_example_count=len(selected_outcomes),
                    quorum_probability=quorum_probability,
                    recommendation_source=recommendation_source,
                    model=model_status,
                    candidate_reference_scope=reference_scope,
                    assumed_min_capacity=assumed_min_capacity,
                    assumed_max_capacity=assumed_max_capacity,
                    confidence_score=None,
                    observed_search_count=count,
                    window_days=window_days,
                    analyzed_at=analyzed_at,
                )
            )
        return suggestions


class DatabaseUnmetDemandRecorder:
    """Guarda cada señal de demanda en una sesión de base de datos independiente."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        """Inicializa el registrador con una fábrica de sesiones independientes.

        Args:
            session_factory (Callable[[], Session]): Crea una sesión SQLAlchemy nueva.
        """
        self._session_factory = session_factory

    def record_unmet_search(self, *, category: str, zone: str) -> None:
        """Guarda una búsqueda vacía clasificada y controla su transacción.

        Args:
            category (str): Nombre de la categoría verificada.
            zone (str): Zona canónica del establecimiento.
        """
        session = self._session_factory()
        try:
            SearchLogRepository(session).record_unmet_search(
                category=category, zone=zone
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def recorder_for_catalog_session(db: Session) -> DatabaseUnmetDemandRecorder:
    """Crea un registrador independiente usando el motor del catálogo.

    Mantiene la construcción directa de ExperienceService(db), incluso cuando
    la sesión original está ligada a una conexión transaccional de pruebas.

    Args:
        db (Session): Sesión del catálogo cuyo motor o conexión se reutiliza.

    Returns:
        DatabaseUnmetDemandRecorder: Adaptador que abre su propia sesión.
    """
    return DatabaseUnmetDemandRecorder(sessionmaker(bind=db.get_bind()))
