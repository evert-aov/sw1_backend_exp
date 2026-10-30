"""Actualiza PostgreSQL con Alembic y reconoce una instalación inicial no versionada."""

from __future__ import annotations

import ast
from pathlib import Path

import sqlalchemy as sa
from app.core.config import BACKEND_ROOT
from app.core.schema import DatabaseSchemaError, schema_differences, validate_database_schema

BASELINE = "7cfb6d153b7e"
INITIAL_REVISION = BACKEND_ROOT / "alembic/versions/7cfb6d153b7e_initial_schema.py"


def revision_metadata(path: Path = INITIAL_REVISION) -> sa.MetaData:
    """Lee las declaraciones de la revisión inicial sin ejecutarla ni usar una conexión."""
    constructors = {
        "Column", "String", "Text", "UUID", "Integer", "Float", "Numeric", "Boolean",
        "DateTime", "Enum", "JSON", "ForeignKeyConstraint", "PrimaryKeyConstraint",
        "UniqueConstraint", "CheckConstraint",
    }

    def literal(node):
        """Interpreta únicamente literales y constructores SQLAlchemy permitidos."""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple)):
            return [literal(value) for value in node.elts]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            owner, name = node.func.value.id, node.func.attr
            if owner == "op" and name == "f" and len(node.args) == 1:
                return literal(node.args[0])
            if owner == "sa" and name in constructors and all(keyword.arg is not None for keyword in node.keywords):
                return getattr(sa, name)(*[literal(value) for value in node.args], **{keyword.arg: literal(keyword.value) for keyword in node.keywords})
        raise ValueError("La revisión inicial contiene una declaración no admitida para inspección")

    metadata = sa.MetaData()
    module = ast.parse(path.read_text())
    upgrade = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "upgrade")
    for statement in upgrade.body:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            continue
        if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
            raise ValueError("La revisión inicial requiere inspección manual")
        call = statement.value
        if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name) or call.func.value.id != "op":
            raise ValueError("Operación no admitida en la revisión inicial")
        arguments = [literal(value) for value in call.args]
        keywords = {keyword.arg: literal(keyword.value) for keyword in call.keywords}
        if call.func.attr == "create_table":
            sa.Table(arguments[0], metadata, *arguments[1:], **keywords)
        elif call.func.attr == "create_index":
            name, table, columns = arguments
            sa.Index(name, *[metadata.tables[table].c[column] for column in columns], **keywords)
        else:
            raise ValueError("La revisión inicial no es una descripción de esquema compatible")
    return metadata


def unversioned_baseline(connection) -> str | None:
    """Adopta la base inicial solo si tablas, columnas, tipos y restricciones coinciden."""
    from app.core.database import Base, load_all_entities

    load_all_entities()
    tables = set(sa.inspect(connection).get_table_names())
    owned_tables = set(Base.metadata.tables)
    if not tables.intersection(owned_tables):
        return None
    baseline = revision_metadata()
    differences = schema_differences(connection, baseline, exact_columns=True, check_constraints=True)
    for table in sorted(tables.intersection(owned_tables) - set(baseline.tables)):
        differences.append(f"tabla de una migración posterior sin versión: {table}")
    if differences:
        raise DatabaseSchemaError(differences)
    return BASELINE


class MigrationDependencyError(RuntimeError):
    """Dependencia o configuración de migraciones no disponible para arrancar."""


def migration_config():
    """Carga Alembic solo cuando se solicita una migración o revisión del historial."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
    except ImportError as error:
        raise MigrationDependencyError(
            "Falta instalar Alembic en este entorno. Desde experiencia_back ejecuta: "
            "uv pip install --python venv/bin/python -r requirements.txt. "
            "Luego vuelve a iniciar la API o ejecuta venv/bin/python scripts/migrate_database.py."
        ) from error
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise MigrationDependencyError("Se requiere revisar las ramas de migración antes de actualizar.")
    return config, heads[0]


def migrate_connection(connection, config=None) -> None:
    """Migra y valida dentro de la transacción del llamador, con bloqueo compartido."""
    if config is None:
        config, _ = migration_config()
    from alembic import command
    from alembic.runtime.migration import MigrationContext

    config.attributes["connection"] = connection
    # El mismo bloqueo serializa el CLI y los procesos del servidor de desarrollo.
    connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(sa.text("SELECT pg_advisory_xact_lock(hashtext('experiencia_schema_migrations'))"))
    current = MigrationContext.configure(connection).get_current_heads()
    if not current:
        baseline = unversioned_baseline(connection)
        if baseline:
            command.stamp(config, baseline)
    command.upgrade(config, "head")
    validate_database_schema(connection)
