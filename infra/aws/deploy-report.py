#!/usr/bin/env python3
"""Render a safe, machine-readable deployment diagnostic report."""

import json
import re
import sys

PHASES = {"preparation", "build", "publication", "startup", "readiness", "postdeploy"}
STATUSES = {"passed", "failed", "not_verified", "not_applicable"}
SAFE_PROBES = {
    "configuration",
    "github_step_outcome",
    "health_ready",
    "root_contract",
    "compose_up",
    "image_build",
    "ecr_publication",
    "runtime_health_check",
    "runtime_smoke_check",
}
SAFE_EVIDENCE = {
    "attempt",
    "exit_code",
    "outcome",
    "probe",
    "source",
    "status_code",
    "step",
    "exception_type",
}
SAFE_OUTCOMES = {"success", "failure", "cancelled", "skipped", "unknown"}
SAFE_STEPS = {
    "checkout",
    "aws_auth",
    "auth",
    "ecr_login",
    "ecr",
    "buildx_setup",
    "buildx",
    "build",
    "publication",
    "ssm_deploy",
    "setup_pnpm",
    "setup_node",
    "inject_api",
    "install",
    "publish_s3",
    "invalidate_cloudfront",
    "java",
    "flutter",
    "dependencies",
    "analyze",
    "tests",
    "upload_artifact",
    "build_android_apk",
}
FAILURES = {
    "preparation": (
        "DEPLOY.PREPARATION_FAILED",
        "Review validated revision selection, workflow permissions, and required configuration names.",
    ),
    "build": (
        "DEPLOY.BUILD_FAILED",
        "Inspect the build context, Dockerfile, and dependency availability.",
    ),
    "publication": (
        "DEPLOY.PUBLICATION_FAILED",
        "Verify the artifact destination and narrowly scoped publication permissions.",
    ),
    "startup": (
        "DEPLOY.STARTUP_FAILED",
        "Inspect service startup state and deployment configuration without exposing environment values.",
    ),
    "readiness": (
        "DEPLOY.READINESS_FAILED",
        "Check dependency health and the local readiness probe.",
    ),
    "postdeploy": (
        "DEPLOY.POSTDEPLOY_FAILED",
        "Inspect the local postdeploy response and application logs using the release identifier.",
    ),
}
NOT_VERIFIED_ACTIONS = {
    "preparation": "Inspect the preceding workflow steps to identify why preparation was not verified.",
    "build": "Inspect the build and publication job outcomes before attributing a build result.",
    "publication": "Inspect the artifact publication outcome before treating the release as available.",
    "startup": "Run an authorized startup check and preserve its phase report.",
    "readiness": "Run an authorized readiness check; artifact publication does not establish service availability.",
    "postdeploy": "Run an authorized postdeploy smoke check and record its evidence.",
}
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]{1,120}$")
_SAFE_EXCEPTION = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")


def build_report(event):
    phase = event.get("phase")
    status = event.get("status")
    if (
        not isinstance(phase, str)
        or phase not in PHASES
        or not isinstance(status, str)
        or status not in STATUSES
    ):
        raise ValueError("unsupported phase or status")
    service = event.get("service", "experiencia-backend")
    version = event.get("version", "unknown")
    service = (
        service
        if isinstance(service, str) and _SAFE_IDENTIFIER.fullmatch(service)
        else "experiencia-backend"
    )
    version = (
        version if isinstance(version, str) and _SAFE_IDENTIFIER.fullmatch(version) else "unknown"
    )
    report = {
        "schema": "diagnostic-report/v1",
        "service": service[:80],
        "version": version,
        "phase": phase,
        "status": status,
        "code": None,
        "cause_status": "hypothesis" if status == "failed" else "unknown",
        "evidence": {},
        "possible_causes": [],
        "recommended_actions": [],
    }
    evidence = event.get("evidence", {})
    if isinstance(evidence, dict):
        for key, value in evidence.items():
            if key not in SAFE_EVIDENCE:
                continue
            if (
                key in {"attempt", "exit_code", "status_code"}
                and isinstance(value, int)
                and not isinstance(value, bool)
            ):
                report["evidence"][key] = value
            elif key == "probe" and isinstance(value, str) and value in SAFE_PROBES:
                report["evidence"][key] = value
            elif key == "source" and isinstance(value, str) and value in {"github", "ec2"}:
                report["evidence"][key] = value
            elif key == "outcome" and isinstance(value, str) and value in SAFE_OUTCOMES:
                report["evidence"][key] = value
            elif key == "step" and isinstance(value, str) and value in SAFE_STEPS:
                report["evidence"][key] = value
            elif (
                key == "exception_type"
                and isinstance(value, str)
                and _SAFE_EXCEPTION.fullmatch(value)
            ):
                report["evidence"][key] = value
    if status == "failed":
        code, action = FAILURES[phase]
        report["code"] = (
            event.get("code")
            if isinstance(event.get("code"), str)
            and re.fullmatch(r"[A-Z][A-Z0-9_.-]{0,79}", event["code"])
            else code
        )
        cause_status = event.get("cause_status")
        report["cause_status"] = (
            cause_status
            if isinstance(cause_status, str)
            and cause_status in {"confirmed", "hypothesis", "unknown"}
            else "hypothesis"
        )
        report["possible_causes"] = ["The operation for this phase did not complete successfully."]
        report["recommended_actions"] = [action]
    elif status == "not_verified":
        report["recommended_actions"] = [NOT_VERIFIED_ACTIONS[phase]]
    elif status == "not_applicable":
        report["recommended_actions"] = ["This workflow does not execute this runtime phase."]
    return report


def validate_root_contract(payload):
    try:
        response = json.loads(payload)
    except json.JSONDecodeError, TypeError:
        return False
    return (
        isinstance(response, dict)
        and response.get("status") == "online"
        and isinstance(response.get("project"), str)
        and bool(response["project"].strip())
        and isinstance(response.get("version"), str)
        and bool(response["version"].strip())
    )


def main():
    if sys.argv[1:] == ["--validate-root-contract"]:
        return 0 if validate_root_contract(sys.stdin.read()) else 1
    if sys.argv[1:]:
        print("Unsupported diagnostic helper argument.", file=sys.stderr)
        return 2
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        print(json.dumps(build_report(event), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "schema": "diagnostic-report/v1",
                    "service": "experiencia-backend",
                    "version": "unknown",
                    "phase": "preparation",
                    "status": "failed",
                    "code": "DEPLOY.REPORT_INVALID",
                    "cause_status": "confirmed",
                    "evidence": {"exception_type": type(error).__name__},
                    "possible_causes": ["The report event did not match the supported schema."],
                    "recommended_actions": [
                        "Correct the phase event fields and rerun local report validation."
                    ],
                },
                sort_keys=True,
            )
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
