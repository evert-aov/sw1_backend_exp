"""Regresión PostgreSQL del detalle de catálogo al migrar reservas antiguas."""

from datetime import datetime, timedelta, timezone
import socket
from unittest.mock import patch
from uuid import uuid4
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import BACKEND_ROOT, settings
from app.core import database
from app.core.migrations import BASELINE, revision_metadata
from app.core.schema import DatabaseSchemaError, validate_database_schema
from app.experience.service.experience_service import ExperienceService
from scripts import migrate_database


@pytest.mark.parametrize("fresh_database", [True, False], ids=["empty-startup", "legacy-catalog"])
def test_database_migrations_support_new_and_legacy_installations(fresh_database):
    """Inicializa una base vacía o conserva reservas al actualizar la instalación antigua."""
    command = pytest.importorskip("alembic.command", reason="Alembic no instalado: migración PostgreSQL real no verificada")
    from alembic.config import Config

    url = make_url(settings.database_url)
    try:
        if url.host and url.host.startswith("/"):
            with socket.socket(socket.AF_UNIX) as connection:
                connection.connect(f"{url.host}/.s.PGSQL.{url.port or 5432}")
        else:
            with socket.create_connection((url.host or "localhost", url.port or 5432), timeout=2):
                pass
    except PermissionError:
        pytest.skip("PostgreSQL bloqueado por el entorno: migración real no verificada")

    schema = "experiencia_migration_test_" + uuid4().hex
    admin = sa.create_engine(settings.database_url, connect_args={"connect_timeout": 3})
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = sa.create_engine(url.difference_update_query(["options"]), connect_args={
            "connect_timeout": 3, "options": f"-csearch_path={schema} -ctimezone=UTC",
        })
        if fresh_database:
            # Reproduce el comando del usuario y un segundo arranque del reloader.
            with patch.object(database, "engine", engine), patch.object(settings, "DB_SYNCHRONIZE", True):
                database.init_db()
                database.init_db()
            with engine.connect() as connection:
                assert connection.scalar(sa.text("SELECT current_schema()")) == schema
                validate_database_schema(connection)
                from alembic.script import ScriptDirectory
                from alembic.config import Config
                expected_head = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini"))).get_current_head()
                assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == expected_head
                assert connection.scalar(sa.text("SELECT count(*) FROM users")) == 0
            return
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        baseline = revision_metadata()
        host_id, category_id, experience_id, booking_id = (uuid4() for _ in range(4))
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with engine.begin() as connection:
            assert connection.scalar(sa.text("SELECT current_schema()")) == schema
            config.attributes["connection"] = connection
            command.upgrade(config, BASELINE)
            connection.execute(baseline.tables["users"].insert().values(
                id=host_id, first_name="Migration test", email=f"{host_id}@example.com",
                hashed_password="not-a-real-password", is_active=True, interests=[], created_at=now,
            ))
            connection.execute(baseline.tables["categories"].insert().values(id=category_id, name="Migration category"))
            connection.execute(baseline.tables["experiences"].insert().values(
                id=experience_id, host_id=host_id, category_id=category_id, title="Existing event",
                description="An existing event must remain readable", modality="VIRTUAL", status="OPEN",
                price=100, min_capacity=1, max_capacity=5, reserved_slots=0,
                event_date=now + timedelta(days=1), duration_minutes=120, created_at=now,
            ))
            connection.execute(baseline.tables["bookings"].insert().values(
                id=booking_id, user_id=host_id, experience_id=experience_id, quantity=1,
                total_amount=100, platform_fee=8, host_payout=92, status="PENDING", created_at=now,
            ))
            # Simula instalación antigua por create_all únicamente dentro del esquema de prueba.
            connection.execute(sa.text("DROP TABLE alembic_version"))
            with pytest.raises(DatabaseSchemaError, match="bookings"):
                validate_database_schema(connection)

        with patch.object(migrate_database.sa, "create_engine", return_value=engine):
            assert migrate_database.main([]) == 0

        with engine.connect() as connection:
            validate_database_schema(connection)
            assert connection.scalar(sa.text("SELECT count(*) FROM bookings")) == 1
        with Session(engine) as session:
            detail = ExperienceService(session).get_experience_by_id(str(experience_id))
            assert detail.id == str(experience_id)
            assert detail.held_slots == 1
            assert detail.available_slots == 4
            assert detail.commission_rate == 0.08
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
