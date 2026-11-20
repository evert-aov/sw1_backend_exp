from __future__ import annotations

import json
import logging
import time
import traceback
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException

REQUEST_ID_HEADER = "X-Request-ID"
_request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
_logger = logging.getLogger("app.diagnostics")


class ErrorCode(StrEnum):
    INTERNAL_ERROR = "COMMON.INTERNAL_ERROR"
    VALIDATION_ERROR = "COMMON.VALIDATION_ERROR"
    CONFIG_MISSING = "CONFIG.MISSING"
    CONFIG_INVALID = "CONFIG.INVALID"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY.UNAVAILABLE"
    DEPENDENCY_TIMEOUT = "DEPENDENCY.TIMEOUT"
    AUTH_UNAUTHENTICATED = "AUTH.UNAUTHENTICATED"
    AUTH_FORBIDDEN = "AUTH.FORBIDDEN"
    RESOURCE_NOT_FOUND = "RESOURCE.NOT_FOUND"
    RESOURCE_CONFLICT = "RESOURCE.CONFLICT"
    RATE_LIMITED = "COMMON.RATE_LIMITED"
    CI_PREPARATION_FAILED = "CI.PREPARATION_FAILED"
    CI_BUILD_FAILED = "CI.BUILD_FAILED"
    CI_PUBLICATION_FAILED = "CI.PUBLICATION_FAILED"
    DEPLOY_PREPARATION_FAILED = "DEPLOY.PREPARATION_FAILED"
    DEPLOY_BUILD_FAILED = "DEPLOY.BUILD_FAILED"
    DEPLOY_PUBLICATION_FAILED = "DEPLOY.PUBLICATION_FAILED"
    DEPLOY_STARTUP_FAILED = "DEPLOY.STARTUP_FAILED"
    DEPLOY_READINESS_FAILED = "DEPLOY.READINESS_FAILED"
    DEPLOY_POSTDEPLOY_FAILED = "DEPLOY.POSTDEPLOY_FAILED"
    DEPLOY_REPORT_INVALID = "DEPLOY.REPORT_INVALID"


class Severity(StrEnum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class CauseStatus(StrEnum):
    CONFIRMED = "confirmed"
    HYPOTHESIS = "hypothesis"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ErrorDefinition:
    code: ErrorCode
    severity: Severity
    summary: str
    possible_causes: tuple[str, ...]
    recommended_actions: tuple[str, ...]


ERROR_CATALOG: dict[ErrorCode, ErrorDefinition] = {
    ErrorCode.INTERNAL_ERROR: ErrorDefinition(
        ErrorCode.INTERNAL_ERROR,
        Severity.CRITICAL,
        "The service could not complete the request.",
        ("An unhandled application exception occurred.", "A required dependency failed."),
        ("Search logs by request_id.", "Inspect the recorded exception type and stack frames."),
    ),
    ErrorCode.VALIDATION_ERROR: ErrorDefinition(
        ErrorCode.VALIDATION_ERROR,
        Severity.WARNING,
        "The request did not satisfy the endpoint contract.",
        ("A required field is missing or has an invalid format.",),
        ("Check the request schema and field locations without logging submitted values.",),
    ),
    ErrorCode.CONFIG_MISSING: ErrorDefinition(
        ErrorCode.CONFIG_MISSING,
        Severity.CRITICAL,
        "A required configuration value is missing.",
        ("The deployment environment did not provide a required setting.",),
        (
            "Set the named variable in the deployment secret/configuration store and rerun preflight.",
        ),
    ),
    ErrorCode.CONFIG_INVALID: ErrorDefinition(
        ErrorCode.CONFIG_INVALID,
        Severity.CRITICAL,
        "A configuration value has an invalid type or format.",
        ("A variable does not match the expected type, range, or URL format.",),
        ("Review the reported variable name and expected format; do not print its value.",),
    ),
    ErrorCode.DEPENDENCY_UNAVAILABLE: ErrorDefinition(
        ErrorCode.DEPENDENCY_UNAVAILABLE,
        Severity.ERROR,
        "A required dependency could not be reached.",
        (
            "The dependency is stopped, unreachable, or rejecting connections.",
            "Network policy or credentials may be incorrect.",
        ),
        ("Check dependency health, connectivity, and deployment configuration.",),
    ),
    ErrorCode.DEPENDENCY_TIMEOUT: ErrorDefinition(
        ErrorCode.DEPENDENCY_TIMEOUT,
        Severity.ERROR,
        "A required dependency did not respond before the timeout.",
        ("The dependency is overloaded or network latency exceeded the timeout.",),
        ("Inspect dependency latency and capacity before increasing timeouts.",),
    ),
    ErrorCode.AUTH_UNAUTHENTICATED: ErrorDefinition(
        ErrorCode.AUTH_UNAUTHENTICATED,
        Severity.INFO,
        "Authentication is required.",
        ("The request did not contain a valid authentication token.",),
        ("Authenticate again and verify token expiry and client authorization headers.",),
    ),
    ErrorCode.AUTH_FORBIDDEN: ErrorDefinition(
        ErrorCode.AUTH_FORBIDDEN,
        Severity.WARNING,
        "The authenticated principal is not authorized for this operation.",
        ("The principal lacks a required role or resource permission.",),
        ("Verify the intended role and resource policy without exposing token contents.",),
    ),
    ErrorCode.RESOURCE_NOT_FOUND: ErrorDefinition(
        ErrorCode.RESOURCE_NOT_FOUND,
        Severity.INFO,
        "The requested resource was not found.",
        ("The resource does not exist or is not visible to the caller.",),
        ("Verify the resource identifier and access policy.",),
    ),
    ErrorCode.RESOURCE_CONFLICT: ErrorDefinition(
        ErrorCode.RESOURCE_CONFLICT,
        Severity.WARNING,
        "The request conflicts with the current resource state.",
        ("The resource changed or an operation was already applied.",),
        ("Reload the resource state and retry only if the operation is safe and idempotent.",),
    ),
    ErrorCode.RATE_LIMITED: ErrorDefinition(
        ErrorCode.RATE_LIMITED,
        Severity.WARNING,
        "The request exceeded an allowed rate.",
        ("The caller or a shared client exceeded a configured request limit.",),
        ("Check the rate-limit policy and retry after the indicated interval.",),
    ),
    ErrorCode.CI_PREPARATION_FAILED: ErrorDefinition(
        ErrorCode.CI_PREPARATION_FAILED,
        Severity.ERROR,
        "Continuous-integration preparation did not complete.",
        ("A checkout, toolchain, dependency, analysis, or test step failed.",),
        ("Inspect the first failed CI step and verify its inputs and tool versions.",),
    ),
    ErrorCode.CI_BUILD_FAILED: ErrorDefinition(
        ErrorCode.CI_BUILD_FAILED,
        Severity.ERROR,
        "The CI build did not complete.",
        ("The compiler, bundler, or platform build step reported a failure.",),
        ("Inspect the build step and reproduce it with the repository's documented command.",),
    ),
    ErrorCode.CI_PUBLICATION_FAILED: ErrorDefinition(
        ErrorCode.CI_PUBLICATION_FAILED,
        Severity.ERROR,
        "The CI artifact could not be published.",
        ("Artifact creation or upload failed after build completion.",),
        ("Verify the artifact path, upload step, and retention configuration.",),
    ),
    ErrorCode.DEPLOY_PREPARATION_FAILED: ErrorDefinition(
        ErrorCode.DEPLOY_PREPARATION_FAILED,
        Severity.ERROR,
        "Deployment preparation did not complete.",
        ("Required configuration, permissions, or a deployment dependency may be unavailable.",),
        (
            "Inspect the failed preparation step and validate configuration names without printing values.",
        ),
    ),
    ErrorCode.DEPLOY_BUILD_FAILED: ErrorDefinition(
        ErrorCode.DEPLOY_BUILD_FAILED,
        Severity.ERROR,
        "The deployment artifact could not be built.",
        ("The build context, source, or build dependency may be invalid.",),
        ("Reproduce the exact build locally and inspect the first failing build step.",),
    ),
    ErrorCode.DEPLOY_PUBLICATION_FAILED: ErrorDefinition(
        ErrorCode.DEPLOY_PUBLICATION_FAILED,
        Severity.ERROR,
        "The deployment artifact could not be published.",
        ("The target repository or publication permission may be unavailable.",),
        ("Verify the artifact destination and the narrowly scoped publishing permission.",),
    ),
    ErrorCode.DEPLOY_STARTUP_FAILED: ErrorDefinition(
        ErrorCode.DEPLOY_STARTUP_FAILED,
        Severity.CRITICAL,
        "The deployed service did not start successfully.",
        ("The service process or one of its startup dependencies may have failed.",),
        ("Inspect the sanitized startup report and service logs before retrying the release.",),
    ),
    ErrorCode.DEPLOY_READINESS_FAILED: ErrorDefinition(
        ErrorCode.DEPLOY_READINESS_FAILED,
        Severity.CRITICAL,
        "The deployed service did not become ready.",
        ("A required dependency may be unavailable or initialization may still be in progress.",),
        (
            "Check readiness evidence and dependency health; do not treat publication as availability.",
        ),
    ),
    ErrorCode.DEPLOY_POSTDEPLOY_FAILED: ErrorDefinition(
        ErrorCode.DEPLOY_POSTDEPLOY_FAILED,
        Severity.CRITICAL,
        "A post-deployment contract check failed.",
        ("The service may be serving an incompatible or unhealthy release.",),
        ("Inspect the post-deployment response and rollback status before declaring success.",),
    ),
    ErrorCode.DEPLOY_REPORT_INVALID: ErrorDefinition(
        ErrorCode.DEPLOY_REPORT_INVALID,
        Severity.WARNING,
        "A deployment diagnostic event did not match the report schema.",
        ("The phase, status, or safe evidence fields may be malformed.",),
        ("Correct the report event schema and validate it with the isolated report tests.",),
    ),
}

_SAFE_EVIDENCE_KEYS = {
    "method",
    "route",
    "status_code",
    "exception_type",
    "dependency",
    "duration_ms",
    "config_fields",
    "phase",
    "exit_code",
    "stack_frames",
}
_SAFE_FRAME_KEYS = {"file", "function", "line"}


def normalize_request_id(value: str | None) -> str:
    """Accept only UUID v4 request IDs and replace missing or invalid values."""
    try:
        parsed = uuid.UUID(value) if value is not None else None
        return str(parsed) if parsed is not None and parsed.version == 4 else str(uuid.uuid4())
    except (AttributeError, TypeError, ValueError):
        return str(uuid.uuid4())


def current_request_id() -> str | None:
    return _request_id_context.get()


def error_code_for_status(status_code: int) -> ErrorCode:
    if status_code in {400, 422}:
        return ErrorCode.VALIDATION_ERROR
    if status_code == 401:
        return ErrorCode.AUTH_UNAUTHENTICATED
    if status_code == 403:
        return ErrorCode.AUTH_FORBIDDEN
    if status_code == 404:
        return ErrorCode.RESOURCE_NOT_FOUND
    if status_code == 409:
        return ErrorCode.RESOURCE_CONFLICT
    if status_code == 429:
        return ErrorCode.RATE_LIMITED
    if status_code == 503:
        return ErrorCode.DEPENDENCY_UNAVAILABLE
    if status_code == 504:
        return ErrorCode.DEPENDENCY_TIMEOUT
    if status_code >= 500:
        return ErrorCode.INTERNAL_ERROR
    return ErrorCode.VALIDATION_ERROR


def error_payload(detail: Any, code: ErrorCode, request_id: str | None) -> dict[str, Any]:
    """Agrega metadatos estables y conserva íntegro el campo público `detail`."""
    return {
        "detail": jsonable_encoder(detail),
        "code": code.value,
        "request_id": normalize_request_id(request_id),
    }


def _safe_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in evidence.items():
        if key not in _SAFE_EVIDENCE_KEYS:
            continue
        if key == "stack_frames" and isinstance(value, list):
            safe[key] = [
                {
                    frame_key: frame[frame_key]
                    for frame_key in _SAFE_FRAME_KEYS
                    if frame_key in frame
                }
                for frame in value[-8:]
                if isinstance(frame, dict)
            ]
        elif key == "config_fields" and isinstance(value, (list, tuple)):
            safe[key] = [str(name)[:80] for name in value[:30]]
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value[:160] if isinstance(value, str) else value
    return safe


def _stack_frames(exc: Exception) -> list[dict[str, Any]]:
    return [
        {"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
        for frame in traceback.extract_tb(exc.__traceback__)[-8:]
    ]


def build_diagnostic_event(
    *,
    event: str,
    service: str,
    version: str,
    request_id: str | None,
    error_code: ErrorCode,
    cause_status: CauseStatus,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    definition = ERROR_CATALOG[error_code]
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": definition.severity.value,
        "service": service,
        "version": version,
        "event": event,
        "request_id": normalize_request_id(request_id),
        "error_code": definition.code.value,
        "severity": definition.severity.value,
        "cause_status": cause_status.value,
        "evidence": _safe_evidence(evidence),
        "possible_causes": list(definition.possible_causes),
        "recommended_actions": list(definition.recommended_actions),
    }


def log_diagnostic_event(
    *,
    event: str,
    service: str,
    version: str,
    request_id: str | None,
    error_code: ErrorCode,
    cause_status: CauseStatus,
    evidence: dict[str, Any],
) -> None:
    record = build_diagnostic_event(
        event=event,
        service=service,
        version=version,
        request_id=request_id,
        error_code=error_code,
        cause_status=cause_status,
        evidence=evidence,
    )
    level = {
        Severity.CRITICAL: logging.CRITICAL,
        Severity.ERROR: logging.ERROR,
        Severity.WARNING: logging.WARNING,
        Severity.INFO: logging.INFO,
    }[Severity(record["severity"])]
    _logger.log(level, json.dumps(record, ensure_ascii=False, separators=(",", ":")))


def log_operational_event(
    *,
    event: str,
    service: str,
    version: str,
    level: int = logging.INFO,
    request_id: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": logging.getLevelName(level).lower(),
        "service": service,
        "version": version,
        "event": event,
        "request_id": request_id,
        "evidence": _safe_evidence(evidence or {}),
    }
    _logger.log(level, json.dumps(record, ensure_ascii=False, separators=(",", ":")))


class RequestIdMiddleware:
    """Propaga un identificador validado por cada request HTTP."""

    def __init__(self, app: Any, service: str = "unknown", version: str = "unknown") -> None:
        self.app = app
        self.service = service
        self.version = version

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = normalize_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        token: Token[str | None] = _request_id_context.set(request_id)
        started_at = time.perf_counter()
        response_status: int | None = None

        async def send_with_request_id(message: dict[str, Any]) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            if response_status is not None and response_status < 400:
                route = scope.get("route")
                route_path = getattr(route, "path", None)
                log_operational_event(
                    event="http.request.completed",
                    service=self.service,
                    version=self.version,
                    request_id=request_id,
                    evidence={
                        "method": scope.get("method", ""),
                        "route": route_path or "unmatched",
                        "status_code": response_status,
                        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    },
                )
            _request_id_context.reset(token)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    return str(route_path)[:160] if route_path else "unmatched"


def _contains_submitted_value(value: Any, message: str) -> bool:
    if value is None:
        return False
    if isinstance(value, dict):
        return any(
            _contains_submitted_value(key, message) or _contains_submitted_value(item, message)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(_contains_submitted_value(item, message) for item in value)
    rendered = str(value)
    return bool(rendered) and rendered in message


def _safe_validation_message(error: dict[str, Any]) -> str:
    message = error.get("msg")
    if not isinstance(message, str) or _contains_submitted_value(error.get("input"), message):
        return "Request validation failed."
    return message[:256]


def install_diagnostic_handlers(app: Any, *, service: str, version: str) -> None:
    """Instala respuestas compatibles y logs estructurados para fallos HTTP."""

    def request_id_for(request: Request) -> str:
        return normalize_request_id(
            getattr(request.state, "request_id", None) or current_request_id()
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = request_id_for(request)
        safe_errors = [
            {
                "loc": [
                    part if isinstance(part, int) else str(part)[:80]
                    for part in error.get("loc", ())
                ],
                "msg": _safe_validation_message(error),
                "type": str(error.get("type", "value_error"))[:80],
            }
            for error in exc.errors()
        ]
        log_diagnostic_event(
            event="request.validation_failed",
            service=service,
            version=version,
            request_id=request_id,
            error_code=ErrorCode.VALIDATION_ERROR,
            cause_status=CauseStatus.CONFIRMED,
            evidence={
                "method": request.method,
                "route": _route_template(request),
                "status_code": 422,
            },
        )
        return JSONResponse(
            status_code=422,
            content=error_payload(safe_errors, ErrorCode.VALIDATION_ERROR, request_id),
            headers={REQUEST_ID_HEADER: request_id},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = request_id_for(request)
        code = error_code_for_status(exc.status_code)
        log_diagnostic_event(
            event="request.http_error",
            service=service,
            version=version,
            request_id=request_id,
            error_code=code,
            cause_status=CauseStatus.CONFIRMED,
            evidence={
                "method": request.method,
                "route": _route_template(request),
                "status_code": exc.status_code,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.detail, code, request_id),
            headers={REQUEST_ID_HEADER: request_id, **(exc.headers or {})},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = request_id_for(request)
        log_diagnostic_event(
            event="request.unhandled_exception",
            service=service,
            version=version,
            request_id=request_id,
            error_code=ErrorCode.INTERNAL_ERROR,
            cause_status=CauseStatus.HYPOTHESIS,
            evidence={
                "method": request.method,
                "route": _route_template(request),
                "status_code": 500,
                "exception_type": type(exc).__name__,
                "stack_frames": _stack_frames(exc),
            },
        )
        return JSONResponse(
            status_code=500,
            content=error_payload(
                "Error interno del servidor. Por favor intente más tarde.",
                ErrorCode.INTERNAL_ERROR,
                request_id,
            ),
            headers={REQUEST_ID_HEADER: request_id},
        )
