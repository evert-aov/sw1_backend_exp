#!/usr/bin/env python3
"""Fail-closed, secret-safe gate before any AWS deployment operation."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Literal, Mapping, TypedDict, cast

PROJECT = "sw1_backend_exp"
ENVIRONMENT = "aws-production"
REVISION_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
VALIDATORS = {
    "AWS_DEPLOY_ROLE_ARN": re.compile(
        r"^arn:aws(?:-[a-z0-9-]+)?:iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]+$"
    ),
    "AWS_REGION": re.compile(r"^[a-z]{2}(?:-gov)?-[a-z0-9-]+-[0-9]+$"),
    "AWS_ECR_REPOSITORY_BACKEND": re.compile(
        r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*$"
    ),
    "AWS_EC2_INSTANCE_ID": re.compile(r"^i-(?:[0-9a-f]{8}|[0-9a-f]{17})$"),
}
REQUIRED_VARIABLES = tuple(VALIDATORS)


class PreflightEvidence(TypedDict):
    trigger: str
    ref_class: str
    source_event: str
    source_branch: str
    source_conclusion: str
    confirmation: str
    missing_variables: list[str]
    invalid_variables: list[str]


class PreflightReport(TypedDict):
    schema: str
    project: str
    revision: str
    environment: str
    phase: str
    status: Literal["success", "blocked", "not_configured", "failed"]
    gate_status: Literal["allowed", "blocked"]
    duration_ms: int
    code: str | None
    cause_status: str
    evidence: PreflightEvidence
    possible_causes: list[str]
    recommended_actions: list[str]


def _event_evidence(environment: Mapping[str, str]) -> tuple[bool, dict[str, str], str | None]:
    event_name = environment.get("GITHUB_EVENT_NAME", "")
    ref = environment.get("GITHUB_REF", "")
    revision = environment.get("DEPLOY_REVISION") or environment.get("GITHUB_SHA", "")
    evidence: dict[str, str] = {
        "trigger": "other",
        "ref_class": "not_applicable",
        "source_event": "not_applicable",
        "source_branch": "not_applicable",
        "source_conclusion": "not_applicable",
        "confirmation": "not_applicable",
    }

    if event_name == "workflow_dispatch":
        evidence["trigger"] = "manual"
        evidence["ref_class"] = "main" if ref == "refs/heads/main" else "non_main"
        if ref != "refs/heads/main":
            return False, evidence, "DEPLOY.BRANCH_NOT_ALLOWED"
        evidence["confirmation"] = (
            "confirmed"
            if environment.get("DEPLOY_CONFIRMATION", "").lower() == "true"
            else "not_confirmed"
        )
    else:
        return False, evidence, "DEPLOY.TRIGGER_NOT_ALLOWED"

    if not REVISION_PATTERN.fullmatch(revision):
        return False, evidence, "DEPLOY.REVISION_INVALID"
    return True, evidence, None


def build_preflight_report(environment: Mapping[str, str] | None = None) -> PreflightReport:
    """Return a deployment-report/v1 record without exposing variable values."""
    started = time.perf_counter()
    values = environment if environment is not None else os.environ
    allowed, evidence, code = _event_evidence(values)
    revision = values.get("DEPLOY_REVISION") or values.get("GITHUB_SHA", "")
    revision = revision.lower() if REVISION_PATTERN.fullmatch(revision) else "unknown"

    status = "success"
    cause_status = "unknown"
    actions: list[str] = []
    missing: list[str] = []
    invalid: list[str] = []

    if not allowed:
        status = "blocked"
        cause_status = "confirmed"
        actions = [
            "Run deployment only with workflow_dispatch from main; automatic deployments after CI are disabled."
        ]
    else:
        missing = sorted(name for name in REQUIRED_VARIABLES if not values.get(name, "").strip())
        invalid = sorted(
            name
            for name, validator in VALIDATORS.items()
            if values.get(name, "").strip()
            and (values[name] != values[name].strip() or not validator.fullmatch(values[name]))
        )
        if missing:
            status = "not_configured"
            code = "DEPLOY.CONFIG_NOT_CONFIGURED"
            cause_status = "confirmed"
            actions = [
                "Define the listed GitHub Actions repository variables; never place AWS credentials or variable values in source code or reports."
            ]
        elif invalid:
            status = "failed"
            code = "DEPLOY.CONFIG_INVALID"
            cause_status = "confirmed"
            actions = [
                "Correct the format of the listed GitHub Actions variables and rerun preflight; values are intentionally omitted from this report."
            ]
        elif evidence["confirmation"] != "confirmed":
            status = "blocked"
            code = "DEPLOY.CONFIRMATION_REQUIRED"
            cause_status = "confirmed"
            actions = [
                "Set confirm_deployment to true only after reviewing the revision and confirming the protected aws-production environment."
            ]
        else:
            code = None

    report = {
        "schema": "deployment-report/v1",
        "project": PROJECT,
        "revision": revision,
        "environment": ENVIRONMENT,
        "phase": "preflight",
        "status": status,
        "gate_status": "allowed" if status == "success" else "blocked",
        "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
        "code": code,
        "cause_status": cause_status,
        "evidence": {
            **evidence,
            "missing_variables": missing,
            "invalid_variables": invalid,
        },
        "possible_causes": [],
        "recommended_actions": actions,
    }
    return cast(PreflightReport, report)


def _write_report(report: PreflightReport, environment: Mapping[str, str]) -> None:
    rendered = json.dumps(report, indent=2, sort_keys=True)
    report_path = environment.get("DEPLOYMENT_REPORT_PATH")
    if report_path:
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")

    output_path = environment.get("GITHUB_OUTPUT")
    if output_path:
        allowed = "true" if report["status"] == "success" else "false"
        revision = report["revision"]
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"allowed={allowed}\nrevision={revision}\n")

    summary_path = environment.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write("## Deployment preflight\n\n")
            summary.write(f"- Project: `{PROJECT}`\n")
            summary.write(f"- Revision: `{report['revision']}`\n")
            summary.write(f"- Environment: `{ENVIRONMENT}`\n")
            summary.write(f"- Phase/status: `preflight` / **{report['status']}**\n")
            summary.write(f"- Deployment gate: **{report['gate_status']}**\n")
            if report["code"]:
                summary.write(f"- Code: `{report['code']}`\n")
            evidence = report["evidence"]
            if evidence["missing_variables"]:
                summary.write(
                    "- Missing variables: "
                    + ", ".join(f"`{name}`" for name in evidence["missing_variables"])
                    + "\n"
                )
            if evidence["invalid_variables"]:
                summary.write(
                    "- Invalid-format variables: "
                    + ", ".join(f"`{name}`" for name in evidence["invalid_variables"])
                    + "\n"
                )
            for action in report["recommended_actions"]:
                summary.write(f"- Action: {action}\n")
            summary.write("\n```json\n" + rendered + "\n```\n")


def main() -> int:
    environment = os.environ
    report = build_preflight_report(environment)
    _write_report(report, environment)
    print(f"Deployment preflight: {report['status']} ({report['code'] or 'no error'})")
    evidence = report["evidence"]
    if isinstance(evidence, dict):
        for key in ("missing_variables", "invalid_variables"):
            names = evidence.get(key)
            if isinstance(names, list) and names:
                print(f"{key.replace('_', ' ').title()}: {', '.join(names)}")
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
