"""Negative and positive tests for the no-cloud deployment preflight gate."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from infra.aws.deploy_preflight import build_preflight_report

ROOT = Path(__file__).resolve().parents[1]
REVISION = "a" * 40


def valid_environment(**overrides: str) -> dict[str, str]:
    values = {
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": REVISION,
        "WORKFLOW_RUN_EVENT": "",
        "WORKFLOW_RUN_BRANCH": "",
        "WORKFLOW_RUN_CONCLUSION": "",
        "AWS_DEPLOY_ROLE_ARN": "arn:aws:iam::123456789012:role/deploy-role",
        "AWS_REGION": "us-west-2",
        "AWS_ECR_REPOSITORY_BACKEND": "backend-api",
        "AWS_EC2_INSTANCE_ID": "i-0123456789abcdef0",
        "DEPLOY_ENVIRONMENT": "aws-production",
    }
    values.update(overrides)
    return values


def test_preflight_report_matches_stable_deployment_contract() -> None:
    report = build_preflight_report(valid_environment())
    required_fields = {
        "schema",
        "project",
        "revision",
        "environment",
        "phase",
        "status",
        "duration_ms",
        "gate_status",
        "code",
        "cause_status",
        "evidence",
        "possible_causes",
        "recommended_actions",
    }

    assert required_fields <= report.keys()
    assert report["schema"] == "deployment-report/v1"
    assert isinstance(report["duration_ms"], int)
    assert isinstance(report["evidence"], dict)
    assert isinstance(report["possible_causes"], list)
    assert isinstance(report["recommended_actions"], list)


def test_blocks_manual_dispatch_from_non_main_without_echoing_ref() -> None:
    report = build_preflight_report(valid_environment(GITHUB_REF="refs/heads/feature/unreviewed"))

    assert report["status"] == "blocked"
    assert report["gate_status"] == "blocked"
    assert report["code"] == "DEPLOY.BRANCH_NOT_ALLOWED"
    assert report["cause_status"] == "confirmed"
    assert report["evidence"]["ref_class"] == "non_main"
    assert "feature/unreviewed" not in json.dumps(report)


def test_blocks_workflow_run_unless_successful_push_from_main() -> None:
    report = build_preflight_report(
        valid_environment(
            GITHUB_EVENT_NAME="workflow_run",
            WORKFLOW_RUN_EVENT="pull_request",
            WORKFLOW_RUN_BRANCH="feature/unreviewed",
            WORKFLOW_RUN_CONCLUSION="success",
            DEPLOY_REVISION=REVISION,
        )
    )

    assert report["status"] == "blocked"
    assert report["code"] == "DEPLOY.VALIDATION_NOT_PASSED"
    assert report["evidence"]["source_event"] == "pull_request"


def test_marks_missing_aws_variables_not_configured_without_values() -> None:
    environment = valid_environment(AWS_REGION="", AWS_EC2_INSTANCE_ID="")
    report = build_preflight_report(environment)

    assert report["status"] == "not_configured"
    assert report["gate_status"] == "blocked"
    assert report["code"] == "DEPLOY.CONFIG_NOT_CONFIGURED"
    assert report["evidence"]["missing_variables"] == [
        "AWS_EC2_INSTANCE_ID",
        "AWS_REGION",
    ]
    assert "us-west-2" not in json.dumps(report)


def test_rejects_invalid_configuration_without_echoing_values() -> None:
    bad_region = "not-a-real-region"
    report = build_preflight_report(valid_environment(AWS_REGION=bad_region))

    assert report["status"] == "failed"
    assert report["gate_status"] == "blocked"
    assert report["code"] == "DEPLOY.CONFIG_INVALID"
    assert report["evidence"]["invalid_variables"] == ["AWS_REGION"]
    assert bad_region not in json.dumps(report)


def test_rejects_whitespace_around_values_consumed_verbatim() -> None:
    report = build_preflight_report(valid_environment(AWS_ECR_REPOSITORY_BACKEND=" backend-api "))

    assert report["status"] == "failed"
    assert report["gate_status"] == "blocked"
    assert report["evidence"]["invalid_variables"] == ["AWS_ECR_REPOSITORY_BACKEND"]
    assert " backend-api " not in json.dumps(report)


def test_accepts_valid_main_dispatch_and_successful_main_push() -> None:
    dispatch = build_preflight_report(valid_environment())
    push = build_preflight_report(
        valid_environment(
            GITHUB_EVENT_NAME="workflow_run",
            WORKFLOW_RUN_EVENT="push",
            WORKFLOW_RUN_BRANCH="main",
            WORKFLOW_RUN_CONCLUSION="success",
            DEPLOY_REVISION=REVISION,
        )
    )

    assert dispatch["status"] == push["status"] == "success"
    assert dispatch["gate_status"] == push["gate_status"] == "allowed"
    assert dispatch["revision"] == push["revision"] == REVISION
    assert dispatch["schema"] == push["schema"] == "deployment-report/v1"


def test_cli_writes_safe_json_markdown_and_closed_output(tmp_path: Path) -> None:
    report_path = tmp_path / "deploy-report.json"
    output_path = tmp_path / "github-output.txt"
    summary_path = tmp_path / "github-summary.md"
    environment = valid_environment(AWS_REGION="")
    environment.update(
        {
            "DEPLOYMENT_REPORT_PATH": str(report_path),
            "GITHUB_OUTPUT": str(output_path),
            "GITHUB_STEP_SUMMARY": str(summary_path),
        }
    )

    result = subprocess.run(
        [sys.executable, str(ROOT / "infra/aws/deploy_preflight.py")],
        cwd=ROOT,
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "not_configured"
    assert report["gate_status"] == "blocked"
    assert "allowed=false" in output_path.read_text(encoding="utf-8")
    assert "Deployment preflight" in summary_path.read_text(encoding="utf-8")
    assert "AWS_REGION" in result.stdout
    assert "us-west-2" not in result.stdout
