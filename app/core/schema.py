"""Comprueba que PostgreSQL pueda atender el modelo antes de aceptar solicitudes."""

from __future__ import annotations

from collections.abc import Iterable
import sqlalchemy as sa
from sqlalchemy.engine import Connection

MIGRATION_COMMAND = "venv/bin/python scripts/migrate_database.py"


class DatabaseSchemaError(RuntimeError):
    """Describe diferencias de estructura sin incluir credenciales ni filas privadas."""

    def __init__(self, differences: Iterable[str]):
        """Conserva el detalle completo y presenta una instrucción operativa breve."""
        self.differences = tuple(differences)
        detail = "; ".join(self.differences[:10])
        if len(self.differences) > 10:
            detail += f"; y {len(self.differences) - 10} diferencias más"
        super().__init__(
            f"Esquema PostgreSQL incompatible: {detail}. "
            f"Desde experiencia_back ejecuta: {MIGRATION_COMMAND}. "
            "No reinicies ni vacíes la base para corregirlo."
        )


def equivalent_type(expected: sa.types.TypeEngine, actual: sa.types.TypeEngine, dialect) -> bool:
    """Compara tipos reflejados considerando los alias FLOAT/DOUBLE de PostgreSQL."""
    if isinstance(expected, sa.Float) and isinstance(actual, sa.Float):
        return True
    if isinstance(expected, sa.Enum) and isinstance(actual, sa.Enum):
        return expected.name == actual.name and expected.enums == actual.enums
    return str(expected.compile(dialect=dialect)).upper() == str(actual.compile(dialect=dialect)).upper()


def schema_differences(
    connection: Connection,
    metadata: sa.MetaData,
    *,
    exact_columns: bool = False,
    check_constraints: bool = False,
) -> list[str]:
    """Inspecciona tablas/columnas/tipos; opcionalmente verifica la revisión inicial."""
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    differences = []
    for table in metadata.sorted_tables:
        if table.name not in tables:
            differences.append(f"falta tabla {table.name}")
            continue
        actual = {column["name"]: column for column in inspector.get_columns(table.name)}
        expected_names = set(table.c.keys())
        for column in table.c:
            reflected = actual.get(column.name)
            if reflected is None:
                differences.append(f"falta columna {table.name}.{column.name}")
            elif not equivalent_type(column.type, reflected["type"], connection.dialect):
                differences.append(f"tipo incompatible de {table.name}.{column.name}")
            elif check_constraints and column.nullable != reflected["nullable"]:
                differences.append(f"nulabilidad incompatible de {table.name}.{column.name}")
        if exact_columns:
            for column in sorted(actual.keys() - expected_names):
                differences.append(f"columna no prevista {table.name}.{column}")
        if not check_constraints:
            continue
        expected_pk = tuple(column.name for column in table.primary_key.columns)
        actual_pk = tuple(inspector.get_pk_constraint(table.name).get("constrained_columns") or ())
        if expected_pk != actual_pk:
            differences.append(f"clave primaria incompatible de {table.name}")
        indexes = {index["name"]: index for index in inspector.get_indexes(table.name)}
        unique_columns = {tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints(table.name)}
        unique_columns.update(tuple(index["column_names"]) for index in indexes.values() if index.get("unique"))
        for index in table.indexes:
            reflected = indexes.get(index.name)
            names = tuple(column.name for column in index.columns)
            if reflected is None or tuple(reflected["column_names"]) != names or bool(reflected["unique"]) != bool(index.unique):
                differences.append(f"índice incompatible {index.name}")
        for constraint in table.constraints:
            if isinstance(constraint, sa.UniqueConstraint) and tuple(column.name for column in constraint.columns) not in unique_columns:
                differences.append(f"restricción única ausente de {table.name}")
        actual_fks = set()
        for foreign_key in inspector.get_foreign_keys(table.name):
            action = foreign_key.get("options", {}).get("ondelete")
            if action == "NO ACTION":
                action = None
            actual_fks.add((tuple(foreign_key["constrained_columns"]), foreign_key["referred_table"], tuple(foreign_key["referred_columns"]), action))
        for constraint in table.foreign_key_constraints:
            elements = list(constraint.elements)
            signature = (tuple(element.parent.name for element in elements), elements[0].column.table.name, tuple(element.column.name for element in elements), constraint.ondelete)
            if signature not in actual_fks:
                differences.append(f"clave foránea incompatible de {table.name}")
    return differences


def validate_database_schema(connection: Connection) -> None:
    """Rechaza un esquema antiguo antes de que una ruta provoque UndefinedColumn."""
    from app.core.database import Base, load_all_entities

    load_all_entities()
    differences = schema_differences(connection, Base.metadata)
    if differences:
        raise DatabaseSchemaError(differences)
