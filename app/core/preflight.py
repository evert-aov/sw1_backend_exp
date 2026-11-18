from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text

from app.core.diagnostics import ERROR_CATALOG, ErrorCode

ConnectionFactory = Callable[[], Any]
SettingsFactory = Callable[[], Any]


def _report(
    *,
    phase: str,
    status: str,
    service: str,
    version: str,
    error_code: ErrorCode | None = None,
    cause_status: str = "unknown",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    definition = ERROR_CATALOG.get(error_code) if error_code is not None else None
    return {
        "schema": "diagnostic-report/v1",
        "phase": phase,
        "status": status,
        "service": service,
        "version": version,
        "code": error_code.value if error_code is not None else None,
        "severity": definition.severity.value if definition is not None else "info",
        "cause_status": cause_status,
        "evidence": evidence or {},
        "possible_causes": list(definition.possible_causes) if definition is not None else [],
        "recommended_actions": list(definition.recommended_actions)
        if definition is not None
        else [],
    }


def _validation_report(exc: ValidationError) -> dict[str, Any]:
    validation_errors = exc.errors(include_input=False)
    fields = sorted({".".join(str(part) for part in error["loc"]) for error in validation_errors})
    missing_only = bool(validation_errors) and all(
        error.get("type") == "missing" for error in validation_errors
    )
    return _report(
        phase="configuration",
        status="failed",
        service="experiencia-api",
        version="unknown",
        error_code=ErrorCode.CONFIG_MISSING if missing_only else ErrorCode.CONFIG_INVALID,
        cause_status="confirmed",
        evidence={"config_fields": fields},
    )


def _configuration_report(
    settings_factory: SettingsFactory | None,
) -> tuple[Any | None, dict[str, Any]]:
    try:
        if settings_factory is None:
            from app.core.config import Settings

            # Pyright no modela los campos obligatorios que pydantic-settings carga del entorno.
            settings = Settings()  # pyright: ignore[reportCallIssue]
        else:
            settings = settings_factory()
        # El acceso a database_url valida el esquema sin abrir una conexión.
        settings.database_url
    except ValidationError as exc:
        return None, _validation_report(exc)
    except Exception as exc:
        return None, _report(
            phase="configuration",
            status="failed",
            service="experiencia-api",
            version="unknown",
            error_code=ErrorCode.CONFIG_INVALID,
            cause_status="confirmed",
            evidence={
                "config_fields": ["DATABASE_URL", "DB_USER", "DB_NAME"],
                "exception_type": type(exc).__name__,
            },
        )

    return settings, _report(
        phase="configuration",
        status="passed",
        service=str(getattr(settings, "PROJECT_NAME", "experiencia-api")),
        version=str(getattr(settings, "VERSION", "unknown")),
        evidence={"config_fields": []},
    )


def _connectivity_report(
    settings: Any,
    connection_factory: ConnectionFactory | None,
) -> dict[str, Any]:
    if connection_factory is None:
        from app.core.database import engine

        connection_factory = engine.connect
    try:
        with connection_factory() as connection:
            connection.execute(text("SELECT 1"))
    except TimeoutError as exc:
        return _report(
            phase="connectivity",
            status="failed",
            service=str(getattr(settings, "PROJECT_NAME", "experiencia-api")),
            version=str(getattr(settings, "VERSION", "unknown")),
            error_code=ErrorCode.DEPENDENCY_TIMEOUT,
            cause_status="hypothesis",
            evidence={"dependency": "postgresql", "exception_type": type(exc).__name__},
        )
    except Exception as exc:
        return _report(
            phase="connectivity",
            status="failed",
            service=str(getattr(settings, "PROJECT_NAME", "experiencia-api")),
            version=str(getattr(settings, "VERSION", "unknown")),
            error_code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            cause_status="hypothesis",
            evidence={"dependency": "postgresql", "exception_type": type(exc).__name__},
        )

    return _report(
        phase="connectivity",
        status="passed",
        service=str(getattr(settings, "PROJECT_NAME", "experiencia-api")),
        version=str(getattr(settings, "VERSION", "unknown")),
        evidence={"dependency": "postgresql", "check": "SELECT 1"},
    )


def run_preflight(
    *,
    settings_factory: SettingsFactory | None = None,
    check_connectivity: bool = False,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, Any]:
    """Valida configuración y opcionalmente comprueba PostgreSQL sin modificar datos."""
    settings, report = _configuration_report(settings_factory)
    if settings is None or not check_connectivity:
        return report
    return _connectivity_report(settings, connection_factory)
