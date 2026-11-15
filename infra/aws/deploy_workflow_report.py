#!/usr/bin/env python3
"""Render safe phase reports from GitHub Actions and EC2 deployment outcomes."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Mapping

SERVICE = "experiencia-backend"
REMOTE_PHASES = {"preparation", "startup", "readiness", "postdeploy"}
RUNTIME_PHASES = ("startup", "readiness", "postdeploy")
SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_]*(?:\.[A-Z][A-Z0-9_]*)+$")
SAFE_PROBES = {
    "configuration",
    "preparation_operation",
    "compose_up",
    "health_ready",
    "root_contract",
}
STEP_OUTCOMES = {"success", "failure", "cancelled", "skipped"}


def _report(
    phase: str,
    status: str,
    *,
    version: str,
    evidence: dict[str, object],
    code: str | None = None,
    cause_status: str | None = None,
) -> dict[str, object]:
    failed = status == "failed"
    safe_cause_status = (
        cause_status
        if cause_status in {"confirmed", "hypothesis", "unknown"}
        else "hypothesis"
        if failed
        else "unknown"
    )
    return {
        "schema": "diagnostic-report/v1",
        "service": SERVICE,
        "version": version,
        "phase": phase,
        "status": status,
        "code": code,
        "cause_status": safe_cause_status,
        "evidence": evidence,
        "possible_causes": (
            [
                "A reported step failed; inspect its named Actions or SSM evidence to confirm the cause."
            ]
            if failed
            else []
        ),
        "recommended_actions": (
            ["Inspect the first failed step and its sanitized report before retrying the release."]
            if failed
            else []
        ),
    }


def _step_phase(
    phase: str,
    steps: tuple[str, ...],
    outcomes: Mapping[str, str],
    *,
    version: str,
    error_code: str,
) -> dict[str, object]:
    observed = []
    for step in steps:
        outcome = outcomes.get(step, "unknown") or "unknown"
        if outcome not in STEP_OUTCOMES:
            outcome = "unknown"
        observed.append({"step": step, "outcome": outcome})
    first_failure = next(
        (item for item in observed if item["outcome"] in {"failure", "cancelled"}),
        None,
    )
    if first_failure is not None:
        status = "failed"
        code = error_code
    elif all(item["outcome"] == "success" for item in observed):
        status = "passed"
        code = None
    else:
        status = "not_verified"
        code = None
    return _report(
        phase,
        status,
        version=version,
        code=code,
        evidence={"probe": "github_step_outcomes", "source": "github", "steps": observed},
    )


def _remote_reports(raw_lines: str, version: str) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    for line in raw_lines.splitlines():
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict) or raw.get("schema") != "diagnostic-report/v1":
            continue
        raw_phase = raw.get("phase")
        if (
            raw.get("service") != SERVICE
            or not isinstance(raw_phase, str)
            or raw_phase not in REMOTE_PHASES
        ):
            continue
        status = raw.get("status")
        if not isinstance(status, str) or status not in {
            "passed",
            "failed",
            "not_verified",
            "not_applicable",
        }:
            continue
        phase = "remote_preparation" if raw_phase == "preparation" else raw_phase
        raw_code = raw.get("code")
        code = raw_code if isinstance(raw_code, str) and SAFE_CODE.fullmatch(raw_code) else None
        raw_cause_status = raw.get("cause_status")
        cause_status = (
            raw_cause_status
            if isinstance(raw_cause_status, str)
            and raw_cause_status in {"confirmed", "hypothesis", "unknown"}
            else None
        )
        raw_evidence = raw.get("evidence")
        safe_evidence: dict[str, object] = {"source": "ec2"}
        if isinstance(raw_evidence, dict):
            probe = raw_evidence.get("probe")
            if isinstance(probe, str) and probe in SAFE_PROBES:
                safe_evidence["probe"] = probe
            for key in ("attempt", "exit_code"):
                value = raw_evidence.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    safe_evidence[key] = value
        reports.append(
            _report(
                phase,
                status,
                version=version,
                evidence=safe_evidence,
                code=code,
                cause_status=cause_status,
            )
        )
    return reports


def build_workflow_reports(
    outcomes: Mapping[str, str],
    *,
    version: str = "unknown",
    remote_phase_reports: str = "",
) -> list[dict[str, object]]:
    """Build stage-separated reports without including any environment values."""
    if not re.fullmatch(r"[a-fA-F0-9]{40}", version):
        version = "unknown"
    reports = [
        _step_phase(
            "preparation",
            ("checkout", "buildx"),
            outcomes,
            version=version,
            error_code="DEPLOY.PREPARATION_FAILED",
        ),
        _step_phase(
            "authentication",
            ("aws_auth", "ecr_login"),
            outcomes,
            version=version,
            error_code="DEPLOY.AUTHENTICATION_FAILED",
        ),
        _step_phase(
            "build",
            ("build",),
            outcomes,
            version=version,
            error_code="DEPLOY.BUILD_FAILED",
        ),
        _step_phase(
            "publication",
            ("tag_ecr", "publish"),
            outcomes,
            version=version,
            error_code="DEPLOY.PUBLICATION_FAILED",
        ),
        _step_phase(
            "deployment",
            ("deploy",),
            outcomes,
            version=version,
            error_code="DEPLOY.DEPLOYMENT_FAILED",
        ),
    ]
    remote = _remote_reports(remote_phase_reports, version)
    reports.extend(remote)
    remote_phases = {str(report["phase"]) for report in remote}
    for phase in RUNTIME_PHASES:
        if phase not in remote_phases:
            reports.append(
                _report(
                    phase,
                    "not_verified",
                    version=version,
                    evidence={
                        "probe": "runtime_health_check",
                        "source": "ec2",
                        "outcome": "not_observed",
                    },
                )
            )
    return reports


def main() -> None:
    names = ("checkout", "buildx", "aws_auth", "ecr_login", "tag_ecr", "build", "publish", "deploy")
    outcomes = {name: os.environ.get(f"{name.upper()}_OUTCOME", "unknown") for name in names}
    version = os.environ.get("VERSION", "unknown") or "unknown"
    if not re.fullmatch(r"[a-fA-F0-9]{40}", version):
        version = "unknown"
    reports = build_workflow_reports(
        outcomes,
        version=version,
        remote_phase_reports=os.environ.get("REMOTE_PHASE_REPORTS", ""),
    )
    rendered = json.dumps(reports, indent=2, sort_keys=True)
    print(rendered)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("## Deployment diagnostic report\n\n")
            stream.write(
                "Preflight configuration is reported separately; runtime phases are included only when EC2 returns structured evidence.\n\n"
            )
            stream.write("```json\n" + rendered + "\n```\n")


if __name__ == "__main__":
    main()
