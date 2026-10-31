"""Pruebas unitarias de matching, recomendaciones, demanda predictiva y notificaciones."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.booking.service.booking_service import BookingService
from app.booking.repository.booking_repository import BookingRepository
from app.core.security import create_access_token
from app.experience.dto.experience_dto import ExperienceFilterDTO
from app.experience.entity.experience import Experience, ExperienceStatusEnum, ModalityEnum
from app.matching.dto.matching_dto import (
    MatchingApplicationDTO,
    MatchingGroupResponseDTO,
    SearchLogDTO,
    UnmetDemandInsightDTO,
    ExperienceRecommendationDTO,
)
from app.matching.entity.matching_group import MatchingGroup, MatchingGroupStatusEnum
from app.matching.mapper.matching_mapper import MatchingMapper
from app.matching.service.matching_service import (
    MatchingAlgorithmService,
    ExperienceRecommendationService,
    affinity,
    normalized,
    _normalize_interest_label,
    _normalize_interest_tags,
)
from app.matching.service.demand_prediction_service import (
    DemandPredictionService,
    observed_preferences,
    search_key,
)
from app.notifications.service import NotificationService


def test_affinity_normalizes_accents_and_is_symmetric_without_fake_default():
    assert normalized("  MÚSICA   en VIVO ") == "musica en vivo"
    assert affinity(["Café", "Música"], ["cafe", "Pintura"]) == pytest.approx(1 / 3)
    assert affinity(["Pintura"], ["Música"]) == 0
    assert affinity([], []) == 0
    assert affinity(["café"], ["CAFE"]) == 1


def test_matching_mapper_transforms_group_and_recommendation_dtos():
    group = SimpleNamespace(
        id=str(uuid4()),
        experience_id=str(uuid4()),
        status=MatchingGroupStatusEnum.OPEN,
        deadline=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    dto = MatchingMapper.to_group_response_dto(
        group=group,
        target_quorum=10,
        current_members=3,
        is_quorum_reached=False,
    )
    assert dto.id == group.id
    assert dto.target_quorum == 10
    assert dto.current_members == 3
    assert dto.status == MatchingGroupStatusEnum.OPEN
    assert dto.is_quorum_reached is False

    exp = SimpleNamespace(
        id=str(uuid4()),
        title="Concierto Jazz",
        category=SimpleNamespace(name="Música"),
        cover_image_url="http://example.com/cover.jpg",
        modality=ModalityEnum.IN_PERSON,
        price=150.0,
        venue=SimpleNamespace(name="Teatro Central", zone="Equipetrol"),
    )
    rec_dto = MatchingMapper.to_recommendation_dto(
        experience=exp,
        event_date=datetime.now(timezone.utc),
        interest_score=0.9,
        matched_interests=["Música", "Jazz"],
        reasons=["Coincide con tu interés: Música", "A 2.5 km"],
        distance_km=2.5,
    )
    assert rec_dto.experience_id == exp.id
    assert rec_dto.title == "Concierto Jazz"
    assert rec_dto.interest_score == 0.9
    assert rec_dto.distance_km == 2.5
    assert len(rec_dto.matched_interests) == 2


def test_experience_recommendation_affinity_filters_stopwords():
    exp = SimpleNamespace(
        title="Taller de Pintura y Café en el Centro",
        description="Aprende acuarela con los mejores artistas",
        category=SimpleNamespace(name="Arte"),
    )
    score, matched = ExperienceRecommendationService._interest_affinity(
        ["Pintura", "Acuarela", "Música"], exp
    )
    assert score > 0.6
    assert "Pintura" in matched
    assert "Música" not in matched


def test_cyclical_feature_encoding_in_demand_prediction():
    features = DemandPredictionService._feature_record(
        zone="Equipetrol",
        category="Gastronomía",
        modality="IN_PERSON",
        price=120.0,
        min_capacity=10,
        max_capacity=50,
        weekday_hour=(4, 18),  # Viernes 18:00
    )
    assert features["zone"] == "equipetrol"
    assert features["category"] == "gastronomía"
    assert "weekday_sin" in features
    assert "weekday_cos" in features
    assert "hour_sin" in features
    assert "hour_cos" in features
    assert pytest.approx(features["capacity_ratio"]) == 0.2


def test_bayesian_quorum_estimation_fallback_requires_minimum_outcomes():
    # Con menos de 10 ejemplos debe devolver INSUFFICIENT_HISTORY
    outcomes = [
        ("Centro", ModalityEnum.IN_PERSON, 100.0, "BOB", datetime.now(timezone.utc), 10, 8),
        ("Centro", ModalityEnum.IN_PERSON, 100.0, "BOB", datetime.now(timezone.utc), 10, 12),
    ]
    prob, source = DemandPredictionService._estimate_quorum_probability(
        outcomes,
        candidate_price=100.0,
        candidate_currency="BOB",
        candidate_time_slot="viernes por la noche",
        candidate_modality="IN_PERSON",
    )
    assert prob is None
    assert source == "INSUFFICIENT_HISTORY"


def test_legacy_log_search_endpoint_returns_410():
    from app.matching.control.demand_controller import log_user_search

    with pytest.raises(HTTPException) as exc_info:
        log_user_search(SearchLogDTO(query_text="jazz", zone="Centro", found_results=False))
    assert exc_info.value.status_code == 410


def test_notification_dedupe_is_per_recipient_kind_and_quorum_generation():
    db = MagicMock()
    notices = NotificationService(db)
    user, event = str(uuid4()), str(uuid4())
    keys = []
    for generation in [1, 1, 2]:
        notices.stage(event, [user, user], "QUORUM_CONFIRMED", generation, "Confirmado")
        statement = db.execute.call_args.args[0]
        values = statement.compile().params
        keys.append([value for key, value in values.items() if key.startswith("dedupe_key")])
        assert "ON CONFLICT" in str(statement)
    assert keys[0] == keys[1] and keys[0] != keys[2]
    assert len(keys[0]) == 1
    db.commit.assert_not_called()


def test_mark_read_cannot_modify_another_users_notice():
    db = MagicMock()
    db.scalar.return_value = None
    with pytest.raises(HTTPException) as error:
        NotificationService(db).mark_read(str(uuid4()), str(uuid4()))
    assert error.value.status_code == 404
    db.commit.assert_not_called()


def test_demand_search_key_deduplicates_retries_and_separates_sessions_windows():
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    filters = {"search": "cafe", "zone": "centro"}
    assert search_key(filters, "a", now) == search_key(dict(reversed(list(filters.items()))), "a", now + timedelta(seconds=1))
    assert search_key(filters, "a", now) != search_key(filters, "b", now)
    assert search_key(filters, "a", now) != search_key(filters, "a", now + timedelta(minutes=5))


def test_observed_preferences_use_median_and_bolivia_time_without_invented_data():
    assert observed_preferences([]) == (None, None)
    price, slot = observed_preferences([{"max_price": 20}, {"max_price": 100, "date_from": "2030-01-01T23:00:00Z"}])
    assert price == 60 and slot == "Noche"


def test_auth_token_cannot_be_used_as_an_entry_qr():
    db = MagicMock()
    with pytest.raises(HTTPException) as error:
        BookingService(db).scan_ticket(create_access_token(str(uuid4())), str(uuid4()))
    assert error.value.status_code == 400
    db.get.assert_not_called()


def test_booking_account_lock_does_not_block_notification_foreign_keys():
    db = MagicMock()
    BookingRepository(db).lock_user(str(uuid4()))
    db.query.return_value.filter.return_value.with_for_update.assert_called_once_with(key_share=True)
