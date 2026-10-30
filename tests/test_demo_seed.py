"""Contrato del dataset y protección de identidades; no simula éxito en PostgreSQL."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from app.auth.entity.user import User
from app.core.database import load_all_entities
from app.core.demo_seed import (
    DEFAULT_DEMO_PASSWORD,
    DemoSeedConflict,
    _ensure,
    build_demo_plan,
    populate_demo,
)
from app.experience.dto.experience_dto import ExperienceCreateDTO, VenueCreateDTO
from scripts import seed_role_demo


def test_plan_covers_roles_ownership_and_valid_capacity():
    plan = build_demo_plan()
    users = {item["key"]: item for item in plan["users"]}
    assert len(users) == 6
    assert users["admin"]["roles"] == ["ADMIN"]
    assert users["host-cultura"]["roles"] == ["HOST"]
    assert set(users["dual"]["roles"]) == {"HOST", "ATTENDEE"}
    venues = {item["id"]: item for item in plan["venues"]}
    for venue in venues.values():
        VenueCreateDTO(**venue["data"])
    assert len(plan["experiences"]) == 10
    for item in plan["experiences"]:
        event = ExperienceCreateDTO(**item["data"])
        assert event.max_capacity >= event.min_capacity
        if event.venue_id:
            assert venues[event.venue_id]["owner_id"] == item["host_id"]
            assert venues[event.venue_id]["data"]["max_capacity"] >= event.max_capacity


def test_free_tickets_and_pending_payment_do_not_fabricate_stripe_transactions():
    plan = build_demo_plan()
    events = {item["id"]: item for item in plan["experiences"]}
    free_seats = sum(
        item["quantity"]
        for item in plan["bookings"]
        if events[item["experience_id"]]["data"]["price"] == 0
    )
    assert free_seats == 4
    assert len(plan["bookings"]) == 4
    assert (
        sum(
            events[item["experience_id"]]["data"]["price"] > 0
            for item in plan["bookings"]
        )
        == 1
    )
    assert "payments" not in plan
    assert all(8 <= len(item["idempotency_key"]) <= 64 for item in plan["bookings"])
    assert all(
        item["search_filters"]["source"] == "demo-seed" for item in plan["searches"]
    )


def test_ids_are_stable_and_datasets_are_independent():
    now = datetime.now(timezone.utc)
    one, repeated, another = (
        build_demo_plan(now=now),
        build_demo_plan(now=now + timedelta(days=2)),
        build_demo_plan("roles-otro", now),
    )
    for kind in ["users", "categories", "venues", "experiences", "searches"]:
        ids = {item["id"] for item in one[kind]}
        assert ids == {item["id"] for item in repeated[kind]}
        assert not ids.intersection(item["id"] for item in another[kind])
    assert {user["email"] for user in one["users"]}.isdisjoint(
        user["email"] for user in another["users"]
    )


@pytest.mark.parametrize("dataset", ["", "../roles", "Roles", "roles demo", "a" * 25])
def test_invalid_dataset_is_rejected(dataset):
    with pytest.raises(ValueError):
        build_demo_plan(dataset)


def test_existing_identity_is_not_overwritten_or_promoted():
    load_all_entities()
    user = User(
        id="existing",
        email="demo@example.com",
        first_name="Edited",
        hashed_password="original-hash",
    )
    db = MagicMock()
    db.get.return_value = user
    result, created = _ensure(
        db,
        User,
        "existing",
        {
            "email": "demo@example.com",
            "first_name": "Reset",
            "hashed_password": "new-hash",
        },
        ("email",),
    )
    assert result is user and not created
    assert user.first_name == "Edited" and user.hashed_password == "original-hash"
    db.add.assert_not_called()
    with pytest.raises(DemoSeedConflict):
        _ensure(db, User, "existing", {"email": "other@example.com"}, ("email",))


def test_seed_requires_outer_transaction_before_any_writes():
    with Session() as db:
        with pytest.raises(ValueError, match="transacción"):
            populate_demo(db, build_demo_plan(), DEFAULT_DEMO_PASSWORD)


def test_plan_command_never_connects_or_hashes_passwords():
    output = StringIO()
    with (
        patch("sys.argv", ["seed_role_demo.py", "--plan"]),
        patch.object(seed_role_demo.engine, "begin") as begin,
        patch("app.core.demo_seed.get_password_hash") as password_hash,
        redirect_stdout(output),
    ):
        assert seed_role_demo.main() == 0
    begin.assert_not_called()
    password_hash.assert_not_called()
    assert len(json.loads(output.getvalue())["users"]) == 6
    assert DEFAULT_DEMO_PASSWORD not in output.getvalue()


def test_connection_failure_never_claims_success_or_prints_secrets():
    output, errors = StringIO(), StringIO()
    secret = "synthetic-seed-secret"
    failure = OperationalError("hidden query", {}, RuntimeError(secret))
    with (
        patch("sys.argv", ["seed_role_demo.py"]),
        patch.dict("os.environ", {"DEMO_SEED_PASSWORD": secret}),
        patch.object(seed_role_demo.engine, "begin", side_effect=failure),
        redirect_stdout(output),
        redirect_stderr(errors),
    ):
        assert seed_role_demo.main() == 2
    assert "Seed confirmado" not in output.getvalue()
    assert secret not in output.getvalue() + errors.getvalue()
