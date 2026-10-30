"""Reglas de matching y evidencia de demanda; estas pruebas no sustituyen PostgreSQL."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError
import pytest
from app.core.config import settings
from app.booking.service.booking_service import BookingService
from app.core.security import create_access_token
from app.experience.dto.experience_dto import ExperienceFilterDTO
from app.matching.dto.matching_dto import MatchingApplicationDTO, SearchLogDTO, UnmetDemandInsightDTO
from app.matching.service.matching_service import MatchingAlgorithmService, affinity, normalized
from app.matching.service.demand_prediction_service import DemandPredictionService, observed_preferences, search_key
from app.notifications.service import NotificationService
from app.booking.repository.booking_repository import BookingRepository


def group_context():
    user_id, event_id = str(uuid4()), str(uuid4())
    event = SimpleNamespace(id=event_id, status="OPEN", reserved_slots=0, title="Taller", min_capacity=2,
                            max_capacity=5, event_date=datetime.now(timezone.utc) + timedelta(days=1), duration_minutes=120,
                            venue=SimpleNamespace(zone="Centro"))
    group = SimpleNamespace(id=str(uuid4()), experience_id=event_id, target_quorum=2, status="OPEN",
                            created_at=datetime.now(timezone.utc), deadline=event.event_date - timedelta(minutes=30),
                            current_members=1, members=[SimpleNamespace(user_id=user_id, preferences={"interests": ["Música"]})])
    service = MatchingAlgorithmService(MagicMock())
    service._context = MagicMock(return_value=(SimpleNamespace(is_active=True), event, ["Música"]))
    service._groups = MagicMock(return_value=[group])
    return service, event, group, user_id


def test_affinity_normalizes_accents_and_is_symmetric_without_fake_default():
    assert normalized("  MÚSICA   en VIVO ") == "musica en vivo"
    assert affinity(["Café", "Música"], ["cafe", "Pintura"]) == pytest.approx(1 / 3)
    assert affinity(["Pintura"], ["Música"]) == 0
    assert affinity([], []) == 0
    assert affinity(["café"], ["CAFE"]) == 1


def test_reading_group_neither_joins_nor_commits_and_preserves_economic_quorum():
    service, event, group, user_id = group_context()
    for _ in range(3):
        result = service.get_group_status(event.id, str(uuid4()))
        assert result.current_members == 1
        assert result.is_member is False
        assert result.experience_confirmed is False
    assert event.reserved_slots == 0
    service.db.add.assert_not_called()
    service.db.commit.assert_not_called()


def test_duplicate_matching_application_keeps_one_membership():
    service, event, group, user_id = group_context()
    result = service.apply_for_matching(user_id, MatchingApplicationDTO(experience_id=event.id))
    assert result.is_member and result.current_members == 1
    service.db.add.assert_not_called()
    assert event.status == "OPEN" and event.reserved_slots == 0


def test_expired_group_is_computed_without_updating_the_database():
    service, event, group, user_id = group_context()
    group.deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
    group.target_quorum = 1
    result = service.get_group_status(event.id, user_id)
    assert result.status == "EXPIRED" and result.is_quorum_reached is False
    assert group.status == "OPEN"
    service.db.commit.assert_not_called()


@pytest.mark.parametrize("preferences", [
    {"preferred_zone": "Otra zona"},
    {"available_from": datetime.now(timezone.utc), "available_to": datetime.now(timezone.utc) + timedelta(hours=1)},
])
def test_incompatible_zone_or_availability_is_rejected_before_membership(preferences):
    service, event, group, user_id = group_context()
    with pytest.raises(HTTPException) as error:
        service.apply_for_matching(user_id, MatchingApplicationDTO(experience_id=event.id, **preferences))
    assert error.value.status_code == 409
    service.db.add.assert_not_called()
    service.db.rollback.assert_called_once()


def test_matching_requires_complete_ordered_availability():
    with pytest.raises(ValidationError):
        MatchingApplicationDTO(experience_id=str(uuid4()), available_from=datetime.now())
    with pytest.raises(ValidationError):
        MatchingApplicationDTO(experience_id=str(uuid4()), available_from=datetime(2030, 1, 2), available_to=datetime(2030, 1, 1))


def test_unknown_venue_zone_does_not_match_a_requested_zone():
    service, event, group, user_id = group_context()
    event.venue.zone = None
    with pytest.raises(HTTPException) as error:
        service.apply_for_matching(user_id, MatchingApplicationDTO(experience_id=event.id, preferred_zone="Centro"))
    assert error.value.status_code == 409


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


def test_catalog_logs_actual_result_and_skips_later_pages():
    db = MagicMock()
    service = DemandPredictionService(db)
    service.record_catalog(ExperienceFilterDTO(search="MÚSICA", zone=" Centro "), 3, "session")
    parameters = db.execute.call_args.args[0].compile().params
    assert parameters["found_results"] is True
    assert parameters["query_text"] == "musica"
    assert parameters["zone"] == "centro"
    db.execute.reset_mock()
    service.record_catalog(ExperienceFilterDTO(search="Música", page=2), 0, "session")
    db.execute.assert_not_called()


def test_client_found_results_is_ignored_and_recomputed():
    service = DemandPredictionService(MagicMock())
    service.record_catalog = MagicMock()
    with patch("app.matching.service.demand_prediction_service.ExperienceRepository.filter", return_value=([], 7)):
        service.record_search(None, SearchLogDTO(query_text="música", zone="Centro", found_results=False))
    assert service.record_catalog.call_args.args[1] == 7


def test_observed_preferences_use_median_and_bolivia_time_without_invented_data():
    assert observed_preferences([]) == (None, None)
    price, slot = observed_preferences([{"max_price": 20}, {"max_price": 100, "date_from": "2030-01-01T23:00:00Z"}])
    assert price == 60 and slot == "Noche"


def test_recommendations_do_not_invent_confidence_or_price_when_missing():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    service = DemandPredictionService(db)
    service.get_zone_insights = MagicMock(return_value=[UnmetDemandInsightDTO(
        id=str(uuid4()), zone="centro", category_keyword="pintura", search_count=3, analyzed_at=datetime.now(),
    )])
    suggestion = service.generate_ai_experience_suggestions()[0]
    assert suggestion.confidence_score is None
    assert suggestion.suggested_price is None
    assert suggestion.estimated_interest_count == 3
    assert suggestion.method == "observed_searches"


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
