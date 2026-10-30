"""Permisos de roles, propiedad y bloqueo de experiencias con participantes."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.core.database import load_all_entities
from app.auth.entity.user import User
from app.auth.dto.auth_dto import LoginDTO
from app.auth.service.auth_service import AuthService
from app.auth.service.profile_service import ProfileService
from app.experience.entity.experience import (
    Experience,
    ExperienceStatusEnum,
    ModalityEnum,
)
from app.experience.entity.venue import Venue
from app.experience.service.experience_service import ExperienceService
from app.experience.service.venue_service import VenueService
from app.experience.dto.experience_dto import (
    ExperienceCreateDTO,
    ExperienceUpdateDTO,
    VenueCreateDTO,
)
from app.admin.controller import AdminRolesDTO, assign_roles


@pytest.fixture(autouse=True)
def models():
    load_all_entities()


@pytest.mark.parametrize(
    "roles,allowed",
    [
        (["HOST"], False),
        (["ADMIN"], False),
        (["VENUE"], False),
        ([], False),
        (["ATTENDEE"], True),
        (["HOST", "ATTENDEE"], True),
    ],
)
def test_mobile_requires_explicit_attendee_before_minting_token(roles, allowed):
    service = AuthService(MagicMock())
    service.user_repo.get_by_email = MagicMock(
        return_value=User(
            id=str(uuid4()),
            first_name="User",
            email="test@example.com",
            hashed_password="unused",
            is_active=True,
        )
    )
    service.user_repo.get_user_roles = MagicMock(return_value=roles)
    with (
        patch("app.auth.service.auth_service.verify_password", return_value=True),
        patch(
            "app.auth.service.auth_service.create_access_token",
            return_value="synthetic-token",
        ) as mint,
    ):
        if allowed:
            assert (
                service.login(
                    LoginDTO(email="test@example.com", password="test"),
                    required_role="ATTENDEE",
                ).roles
                == roles
            )
            mint.assert_called_once()
        else:
            with pytest.raises(HTTPException) as error:
                service.login(
                    LoginDTO(email="test@example.com", password="test"),
                    required_role="ATTENDEE",
                )
            assert error.value.status_code == 403
            mint.assert_not_called()


def event():
    return Experience(
        id=str(uuid4()),
        host_id=str(uuid4()),
        category_id=str(uuid4()),
        title="Event",
        description="An experience",
        modality=ModalityEnum.VIRTUAL,
        event_date=datetime.now(timezone.utc) + timedelta(days=1),
        min_capacity=2,
        max_capacity=5,
        reserved_slots=0,
        status=ExperienceStatusEnum.OPEN,
        bookings=[],
    )


@pytest.mark.parametrize(
    "history,active,members,can_edit,can_delete",
    [
        (None, None, None, True, True),
        ("booking", "paid-or-held", None, False, False),
        ("expired-booking", None, None, True, False),
        (None, None, "member", False, False),
    ],
)
def test_management_preserves_attendance_and_financial_history(
    history, active, members, can_edit, can_delete
):
    db = MagicMock()
    db.scalar.side_effect = [history, active, members]
    result = ExperienceService(db)._management_flags(event())
    assert result["can_edit"] is can_edit
    assert result["can_delete"] is can_delete


def test_edit_locks_and_rechecks_attendance_instead_of_trusting_frontend():
    db = MagicMock()
    service = ExperienceService(db)
    item = event()
    service.experience_repo.get_by_id = MagicMock(return_value=item)
    db.scalar.side_effect = ["booking", "paid", None]
    with pytest.raises(HTTPException) as error:
        service.update_experience(
            item.id, item.host_id, ExperienceUpdateDTO(title="New title")
        )
    assert error.value.status_code == 409
    assert item.title == "Event"
    service.experience_repo.get_by_id.assert_any_call(item.id, for_update=True)
    db.commit.assert_not_called()


def test_delete_never_removes_booking_history_even_after_expiration():
    db = MagicMock()
    service = ExperienceService(db)
    item = event()
    service.experience_repo.get_by_id = MagicMock(return_value=item)
    db.scalar.side_effect = ["expired-booking", None, None]
    with pytest.raises(HTTPException) as error:
        service.delete_experience(item.id, item.host_id)
    assert error.value.status_code == 409
    db.execute.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_another_host_cannot_delete_or_edit_an_experience():
    db = MagicMock()
    service = ExperienceService(db)
    item = event()
    service.experience_repo.get_by_id = MagicMock(return_value=item)
    for action in [
        lambda: service.delete_experience(item.id, str(uuid4())),
        lambda: service.update_experience(
            item.id, str(uuid4()), ExperienceUpdateDTO(title="Stolen")
        ),
    ]:
        with pytest.raises(HTTPException) as error:
            action()
        assert error.value.status_code == 404
    db.commit.assert_not_called()


def test_publication_requires_a_venue_owned_by_the_host():
    db = MagicMock()
    service = ExperienceService(db)
    host = str(uuid4())
    service.category_repo.get_by_id = MagicMock(return_value=object())
    service.venue_repo.get_by_id = MagicMock(
        return_value=Venue(
            id=str(uuid4()),
            owner_id=str(uuid4()),
            name="Foreign venue",
            max_capacity=20,
        )
    )
    dto = ExperienceCreateDTO(
        category_id=str(uuid4()),
        venue_id=str(uuid4()),
        title="New event",
        description="A valid description",
        event_date=datetime.now(timezone.utc) + timedelta(days=1),
        min_capacity=2,
        max_capacity=5,
    )
    with pytest.raises(HTTPException) as error:
        service.create_experience(host, dto)
    assert error.value.status_code == 403
    db.commit.assert_not_called()


def test_configuring_a_foreign_venue_never_changes_it():
    db = MagicMock()
    service = VenueService(db)
    item = Venue(
        id=str(uuid4()), owner_id=str(uuid4()), name="Original", max_capacity=20
    )
    service.venue_repo.get_by_id = MagicMock(return_value=item)
    with pytest.raises(HTTPException) as error:
        service.update_my_venue(
            item.id, str(uuid4()), VenueCreateDTO(name="Hijacked", city="City")
        )
    assert error.value.status_code == 404
    assert item.name == "Original"
    db.commit.assert_not_called()


def test_admin_cannot_remove_own_admin_or_use_permissions_revoked_while_waiting():
    actor = str(uuid4())
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = User(
        id=actor
    )
    with patch(
        "app.admin.service.UserRepository.get_user_roles", return_value=["ADMIN"]
    ):
        with pytest.raises(HTTPException) as error:
            assign_roles(db, actor, actor, ["HOST"])
        assert error.value.status_code == 409
    with patch(
        "app.admin.service.UserRepository.get_user_roles", return_value=["HOST"]
    ):
        with pytest.raises(HTTPException) as error:
            assign_roles(db, actor, str(uuid4()), ["ADMIN"])
        assert error.value.status_code == 403
    db.commit.assert_not_called()


@pytest.mark.parametrize("roles", [[], ["UNKNOWN"]])
def test_admin_rejects_empty_or_unknown_assignments(roles):
    with pytest.raises(ValidationError):
        AdminRolesDTO(roles=roles)


def test_users_cannot_grant_themselves_roles():
    db = MagicMock()
    service = ProfileService(db)
    service.user_repo.get_user_roles = MagicMock(return_value=["ATTENDEE"])
    with pytest.raises(HTTPException) as error:
        service.switch_public_role(str(uuid4()), "HOST")
    assert error.value.status_code == 403
    db.commit.assert_not_called()


def test_admin_cannot_remove_the_last_other_active_administrator():
    db = MagicMock()
    target = User(id=str(uuid4()), is_active=True)
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = target
    db.scalar.return_value = None
    with patch(
        "app.admin.service.UserRepository.get_user_roles", return_value=["ADMIN"]
    ):
        with pytest.raises(HTTPException) as error:
            assign_roles(db, str(uuid4()), target.id, ["HOST"])
    assert error.value.status_code == 409
    db.commit.assert_not_called()


def test_bootstrap_admin_does_not_create_or_reactivate_an_unknown_account():
    from scripts.grant_admin import grant_admin

    db = MagicMock()
    with patch("scripts.grant_admin.UserRepository.get_by_email", return_value=None):
        with pytest.raises(ValueError):
            grant_admin(db, "owner@example.com")
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()
