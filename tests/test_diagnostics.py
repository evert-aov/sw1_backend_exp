from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.config import Settings
from app.core.diagnostics import (
    ERROR_CATALOG,
    ErrorCode,
    RequestIdMiddleware,
    _safe_validation_message,
    install_diagnostic_handlers,
    normalize_request_id,
)
from app.core.preflight import run_preflight
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError


def isolated_settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        JWT_SECRET="test-secret-only",
        DB_USER="tester",
        DB_NAME="test_db",
        **overrides,
    )


def test_settings_reject_out_of_range_and_invalid_duration_values() -> None:
    for overrides in (
        {"DB_PORT": 70000},
        {"PLATFORM_FEE_PERCENTAGE": 100.1},
        {"JWT_EXPIRES_IN": "0d"},
    ):
        try:
            isolated_settings(**overrides)
        except ValidationError:
            continue
        raise AssertionError(f"Configuration accepted an invalid value for {overrides.keys()}")


def test_preflight_reports_missing_configuration_fields_without_values() -> None:
    def missing_settings() -> Settings:
        with patch.dict(os.environ, {}, clear=True):
            # Missing JWT_SECRET is the configuration failure this test must exercise.
            return Settings(
                _env_file=None,  # pyright: ignore[reportCallIssue]
                DB_USER="tester",
                DB_NAME="test_db",
            )

    report = run_preflight(settings_factory=missing_settings)

    assert report["status"] == "failed"
    assert report["code"] == ErrorCode.CONFIG_MISSING.value
    assert "JWT_SECRET" in report["evidence"]["config_fields"]
    assert "tester" not in json.dumps(report)


def test_preflight_reports_invalid_configuration_types_without_values() -> None:
    report = run_preflight(settings_factory=lambda: isolated_settings(DB_PORT=70000))

    assert report["status"] == "failed"
    assert report["code"] == ErrorCode.CONFIG_INVALID.value
    assert "DB_PORT" in report["evidence"]["config_fields"]
    assert "70000" not in json.dumps(report)


def test_preflight_connectivity_failure_is_hypothesis_and_uses_no_real_service() -> None:
    from contextlib import contextmanager

    @contextmanager
    def unreachable_dependency():
        raise TimeoutError("synthetic-sensitive-value")
        yield MagicMock()

    report = run_preflight(
        settings_factory=isolated_settings,
        check_connectivity=True,
        connection_factory=unreachable_dependency,
    )

    assert report["status"] == "failed"
    assert report["code"] == ErrorCode.DEPENDENCY_TIMEOUT.value
    assert report["cause_status"] == "hypothesis"
    assert report["evidence"]["exception_type"] == "TimeoutError"
    assert "synthetic-sensitive-value" not in json.dumps(report)


def build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    install_diagnostic_handlers(app, service="experiencia-api", version="test")

    @app.get("/http-error")
    async def http_error() -> None:
        raise HTTPException(status_code=422, detail={"field": "invalid"})

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("synthetic-sensitive-value")

    @app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/validation")
    async def validation(count: int) -> dict[str, int]:
        return {"count": count}

    return app


def test_normalize_request_id_accepts_uuid_and_replaces_invalid_values() -> None:
    request_id = str(uuid.uuid4())

    assert normalize_request_id(request_id) == request_id
    generated = normalize_request_id("bad\r\ninjected")
    assert generated != "bad\r\ninjected"
    assert str(uuid.UUID(generated)) == generated


def test_request_id_is_echoed_and_attached_to_additive_error_fields() -> None:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "diagnostic-error-contract-v1.json").read_text(
            encoding="utf-8"
        )
    )
    request_id = fixture["request_id"]
    response = TestClient(build_app()).get("/http-error", headers={"X-Request-ID": request_id})

    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == request_id
    assert response.json() == fixture


def test_validation_diagnostics_keep_detail_without_echoing_submitted_values() -> None:
    secret_value = "synthetic-sensitive-value"
    response = TestClient(build_app()).get(f"/validation?count={secret_value}")

    assert response.status_code == 422
    assert response.json()["code"] == ErrorCode.VALIDATION_ERROR.value
    assert response.json()["detail"]
    assert "integer" in response.json()["detail"][0]["msg"]
    assert "input" not in response.json()["detail"][0]
    assert secret_value not in response.text


def test_validation_message_redacts_values_embedded_by_custom_validators() -> None:
    secret_value = "synthetic-sensitive-value"

    message = _safe_validation_message({"msg": f"Rejected {secret_value}.", "input": secret_value})

    assert message == "Request validation failed."
    assert secret_value not in message


def test_invalid_request_id_is_replaced_on_successful_response() -> None:
    response = TestClient(build_app()).get("/ok", headers={"X-Request-ID": "bad\r\ninjected"})

    generated = response.headers["X-Request-ID"]
    assert response.status_code == 200
    assert str(uuid.UUID(generated)) == generated
    assert response.json() == {"ok": True}


def test_non_v4_uuid_request_id_is_replaced() -> None:
    invalid_uuid = "f47ac10b-58cc-11cf-a447-001122334455"
    response = TestClient(build_app()).get("/ok", headers={"X-Request-ID": invalid_uuid})

    assert response.headers["X-Request-ID"] != invalid_uuid
    assert uuid.UUID(response.headers["X-Request-ID"]).version == 4


def test_error_catalog_has_stable_classification_and_actions() -> None:
    definition = ERROR_CATALOG[ErrorCode.INTERNAL_ERROR]

    assert definition.code == "COMMON.INTERNAL_ERROR"
    assert definition.severity == "critical"
    assert definition.possible_causes
    assert definition.recommended_actions
    for code in (
        ErrorCode.DEPLOY_PREPARATION_FAILED,
        ErrorCode.DEPLOY_BUILD_FAILED,
        ErrorCode.DEPLOY_PUBLICATION_FAILED,
        ErrorCode.DEPLOY_STARTUP_FAILED,
        ErrorCode.DEPLOY_READINESS_FAILED,
        ErrorCode.DEPLOY_POSTDEPLOY_FAILED,
        ErrorCode.CI_PREPARATION_FAILED,
        ErrorCode.CI_BUILD_FAILED,
        ErrorCode.CI_PUBLICATION_FAILED,
    ):
        assert ERROR_CATALOG[code].recommended_actions


def test_unhandled_exception_log_is_structured_without_exception_message(caplog) -> None:
    response = TestClient(build_app(), raise_server_exceptions=False).get("/crash")

    assert response.status_code == 500
    log_record = next(record for record in caplog.records if record.name == "app.diagnostics")
    event = json.loads(log_record.message)
    assert event["error_code"] == ErrorCode.INTERNAL_ERROR.value
    assert event["cause_status"] == "hypothesis"
    assert event["evidence"]["exception_type"] == "RuntimeError"
    assert event["request_id"] == response.headers["X-Request-ID"]
    assert "synthetic-sensitive-value" not in log_record.message


def test_existing_root_health_contract_is_preserved_and_correlated() -> None:
    from main import app as service_app

    request_id = str(uuid.uuid4())
    response = TestClient(service_app).get("/", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.json()["status"] == "online"
    assert response.json()["version"]
    assert response.headers["X-Request-ID"] == request_id


def test_main_app_registers_the_shared_safe_unhandled_exception_handler() -> None:
    from main import app as service_app

    handler = service_app.exception_handlers[Exception]
    assert handler.__module__ == "app.core.diagnostics"


def test_http_error_code_and_request_id_are_available_to_cross_origin_clients() -> None:
    from main import app as service_app

    response = TestClient(service_app).get(
        "/does-not-exist", headers={"Origin": "http://localhost:4200"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Not Found"
    assert response.json()["code"] == ErrorCode.RESOURCE_NOT_FOUND.value
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["Access-Control-Expose-Headers"] == "X-Request-ID"


def test_cors_preflight_allows_auth_and_request_correlation_headers() -> None:
    from main import app as service_app

    response = TestClient(service_app).options(
        "/health/ready",
        headers={
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,x-request-id",
        },
    )

    allowed_headers = response.headers.get("Access-Control-Allow-Headers", "").lower()
    assert response.status_code == 200
    assert "authorization" in allowed_headers
    assert "x-request-id" in allowed_headers


def test_liveness_does_not_depend_on_postgres() -> None:
    from main import app as service_app

    with patch("main.engine.connect", side_effect=AssertionError("must not connect")):
        response = TestClient(service_app).get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "live"


def test_readiness_reports_safe_dependency_failure_and_request_id(caplog) -> None:
    from main import app as service_app

    connection = MagicMock()
    connection.__enter__.side_effect = SQLAlchemyError("synthetic-sensitive-value")
    with patch("main.engine.connect", return_value=connection):
        response = TestClient(service_app).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["code"] == ErrorCode.DEPENDENCY_UNAVAILABLE.value
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert "synthetic-sensitive-value" not in response.text
    diagnostic_records = [
        record.message for record in caplog.records if record.name == "app.diagnostics"
    ]
    assert diagnostic_records
    assert all("synthetic-sensitive-value" not in message for message in diagnostic_records)
