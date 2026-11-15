"""Stdlib tests for stage-specific workflow and remote deployment reports."""

from __future__ import annotations

import json
import unittest

from infra.aws.deploy_workflow_report import build_workflow_reports


class WorkflowReportTests(unittest.TestCase):
    def test_authentication_failure_does_not_claim_later_stages_passed(self) -> None:
        reports = build_workflow_reports(
            {
                "checkout": "success",
                "buildx": "success",
                "aws_auth": "failure",
                "ecr_login": "skipped",
                "tag_ecr": "skipped",
                "build": "skipped",
                "publish": "skipped",
                "deploy": "skipped",
            },
            version="a" * 40,
        )
        phases = {report["phase"]: report for report in reports}

        self.assertEqual(phases["authentication"]["status"], "failed")
        self.assertEqual(phases["authentication"]["code"], "DEPLOY.AUTHENTICATION_FAILED")
        self.assertEqual(phases["build"]["status"], "not_verified")
        self.assertEqual(phases["publication"]["status"], "not_verified")
        self.assertEqual(phases["deployment"]["status"], "not_verified")
        self.assertEqual(phases["startup"]["status"], "not_verified")
        self.assertEqual(phases["readiness"]["status"], "not_verified")

    def test_publication_failure_is_distinct_from_deployment_failure(self) -> None:
        reports = build_workflow_reports(
            {
                "checkout": "success",
                "buildx": "success",
                "aws_auth": "success",
                "ecr_login": "success",
                "tag_ecr": "success",
                "build": "success",
                "publish": "failure",
                "deploy": "skipped",
            },
            version="c" * 40,
        )
        phases = {report["phase"]: report for report in reports}

        self.assertEqual(phases["authentication"]["status"], "passed")
        self.assertEqual(phases["publication"]["status"], "failed")
        self.assertEqual(phases["publication"]["code"], "DEPLOY.PUBLICATION_FAILED")
        self.assertEqual(phases["deployment"]["status"], "not_verified")

    def test_remote_readiness_is_preserved_but_unobserved_postdeploy_is_not_verified(self) -> None:
        remote = "\n".join(
            [
                json.dumps(
                    {
                        "schema": "diagnostic-report/v1",
                        "service": "experiencia-backend",
                        "phase": "startup",
                        "status": "passed",
                        "code": None,
                        "cause_status": "unknown",
                        "evidence": {"probe": "compose_up", "attempt": 1},
                    }
                ),
                json.dumps(
                    {
                        "schema": "diagnostic-report/v1",
                        "service": "experiencia-backend",
                        "phase": "readiness",
                        "status": "failed",
                        "code": "DEPLOY.READINESS_FAILED",
                        "cause_status": "confirmed",
                        "evidence": {"probe": "health_ready", "attempt": 12, "exit_code": 1},
                    }
                ),
                json.dumps(
                    {
                        "schema": "diagnostic-report/v1",
                        "service": "other-service",
                        "phase": "readiness",
                        "status": "passed",
                    }
                ),
            ]
        )
        reports = build_workflow_reports({}, version="b" * 40, remote_phase_reports=remote)
        phases = {report["phase"]: report for report in reports}

        self.assertEqual(phases["startup"]["status"], "passed")
        self.assertEqual(phases["readiness"]["status"], "failed")
        self.assertEqual(phases["readiness"]["cause_status"], "confirmed")
        self.assertEqual(phases["postdeploy"]["status"], "not_verified")

    def test_report_omits_untrusted_remote_strings_and_config_values(self) -> None:
        marker = "DO_NOT_EXPOSE_SYNTHETIC_VALUE"
        remote = json.dumps(
            {
                "schema": "diagnostic-report/v1",
                "service": "experiencia-backend",
                "phase": "readiness",
                "status": "failed",
                "code": marker,
                "evidence": {"probe": marker, "output": marker},
            }
        )
        rendered = json.dumps(
            build_workflow_reports(
                {"aws_auth": "success"},
                version=marker,
                remote_phase_reports=remote,
            )
        )

        self.assertNotIn(marker, rendered)


if __name__ == "__main__":
    unittest.main()
