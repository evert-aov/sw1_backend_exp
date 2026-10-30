"""Regresión del error bookings.unit_price ausente y adopción de la revisión inicial."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pytest

from app.core import database
from app.core.schema import DatabaseSchemaError, equivalent_type, schema_differences, validate_database_schema
from app.core.migrations import BASELINE, revision_metadata, unversioned_baseline


def reflected_schema(metadata):
    """Representa introspección del esquema declarado por una revisión, sin simular SQL."""
    inspector = MagicMock()
    inspector.get_table_names.return_value = list(metadata.tables)
    inspector.get_columns.side_effect = lambda table: [
        {"name": column.name, "type": column.type, "nullable": column.nullable}
        for column in metadata.tables[table].c
    ]
    inspector.get_pk_constraint.side_effect = lambda table: {"constrained_columns": list(metadata.tables[table].primary_key.columns.keys())}
    inspector.get_indexes.side_effect = lambda table: [
        {"name": index.name, "column_names": list(index.columns.keys()), "unique": bool(index.unique)}
        for index in metadata.tables[table].indexes
    ]
    inspector.get_unique_constraints.side_effect = lambda table: [
        {"column_names": list(constraint.columns.keys())}
        for constraint in metadata.tables[table].constraints if isinstance(constraint, sa.UniqueConstraint)
    ]
    inspector.get_foreign_keys.side_effect = lambda table: [
        {"constrained_columns": list(constraint.columns.keys()),
         "referred_table": list(constraint.elements)[0].column.table.name,
         "referred_columns": [element.column.name for element in constraint.elements],
         "options": {"ondelete": constraint.ondelete}}
        for constraint in metadata.tables[table].foreign_key_constraints
    ]
    return inspector


def test_initial_revision_snapshot_does_not_use_current_booking_columns():
    """La base se reconoce desde su revisión histórica, no desde un modelo ya ampliado."""
    metadata = revision_metadata()
    assert "bookings" in metadata.tables
    assert "unit_price" not in metadata.tables["bookings"].c
    assert "expires_at" not in metadata.tables["bookings"].c
    assert "revoked_tokens" not in metadata.tables
    assert metadata.tables["bookings"].c.total_amount.type.__class__ is sa.Float


def test_startup_detects_the_reported_missing_booking_column():
    """El esquema antiguo se rechaza antes de ejecutar el SELECT de experiencias."""
    connection = SimpleNamespace(dialect=postgresql.dialect())
    with patch("app.core.schema.sa.inspect", return_value=reflected_schema(revision_metadata())):
        with pytest.raises(DatabaseSchemaError) as error:
            validate_database_schema(connection)
    assert "falta columna bookings.unit_price" in error.value.differences
    assert "falta columna bookings.expires_at" in error.value.differences
    assert "scripts/migrate_database.py" in str(error.value)
    assert "tipo incompatible de experiences.price" in error.value.differences


def test_current_schema_passes_without_modification():
    """La estructura compatible no produce instrucciones DDL de respaldo."""
    database.load_all_entities()
    connection = SimpleNamespace(dialect=postgresql.dialect())
    with patch("app.core.schema.sa.inspect", return_value=reflected_schema(database.Base.metadata)):
        validate_database_schema(connection)


def test_verified_unversioned_initial_schema_can_be_adopted():
    """Solo la estructura inicial equivalente permite registrar esa revisión."""
    connection = SimpleNamespace(dialect=postgresql.dialect())
    inspector = reflected_schema(revision_metadata())
    with patch("app.core.schema.sa.inspect", return_value=inspector):
        assert unversioned_baseline(connection) == BASELINE


def test_partial_schema_is_not_stamped_as_initial():
    """No oculta una columna ya añadida manualmente mediante un stamp arbitrario."""
    metadata = revision_metadata()
    metadata.tables["bookings"].append_column(sa.Column("unit_price", sa.Numeric(14, 2)))
    with patch("app.core.schema.sa.inspect", return_value=reflected_schema(metadata)):
        with pytest.raises(DatabaseSchemaError) as error:
            unversioned_baseline(SimpleNamespace(dialect=postgresql.dialect()))
    assert "columna no prevista bookings.unit_price" in error.value.differences


def test_unversioned_schema_requires_initial_indexes_and_foreign_keys():
    """No adopta tablas solo porque sus nombres coincidan con la revisión inicial."""
    inspector = reflected_schema(revision_metadata())
    inspector.get_indexes.side_effect = None
    inspector.get_indexes.return_value = []
    inspector.get_foreign_keys.side_effect = None
    inspector.get_foreign_keys.return_value = []
    with patch("app.core.schema.sa.inspect", return_value=inspector):
        with pytest.raises(DatabaseSchemaError) as error:
            unversioned_baseline(SimpleNamespace(dialect=postgresql.dialect()))
    assert any("índice incompatible" in difference for difference in error.value.differences)
    assert any("clave foránea incompatible" in difference for difference in error.value.differences)


def test_float_alias_is_supported_but_not_float_instead_of_numeric():
    """La reflexión DOUBLE PRECISION es válida para Float, pero no para dinero Numeric."""
    dialect = postgresql.dialect()
    assert equivalent_type(sa.Float(), postgresql.DOUBLE_PRECISION(), dialect)
    assert not equivalent_type(sa.Numeric(14, 2), postgresql.DOUBLE_PRECISION(), dialect)


def test_connection_failure_or_schema_failure_never_creates_tables():
    """Un esquema incompleto se propaga sin ejecutar create_all ni seeder."""
    with patch.object(database.settings, "DB_SYNCHRONIZE", False), patch.object(database, "engine"), patch("app.core.schema.validate_database_schema", side_effect=DatabaseSchemaError(["falta columna bookings.unit_price"])), patch.object(database.Base.metadata, "create_all") as create:
        with pytest.raises(DatabaseSchemaError):
            database.init_db()
    create.assert_not_called()


def test_empty_database_needs_initial_migration_without_stamping():
    """Una base recién creada se reconoce como nueva y no como instalación antigua."""
    with patch("app.core.migrations.sa.inspect", return_value=reflected_schema(sa.MetaData())):
        assert unversioned_baseline(SimpleNamespace(dialect=postgresql.dialect())) is None
