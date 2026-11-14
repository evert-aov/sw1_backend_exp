import json
import tempfile
import unittest
from pathlib import Path

from scripts.ci.security_report import (
    create_security_report,
    main,
    render_summary,
)


class SecurityReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_scan(
        self,
        filename: str,
        *,
        secrets=None,
        vulnerabilities=None,
        target: str = "tests/fixture.txt",
    ) -> Path:
        result = {"Target": target}
        if secrets is not None:
            result["Secrets"] = secrets
        if vulnerabilities is not None:
            result["Vulnerabilities"] = vulnerabilities
        raw_path = self.directory / filename
        raw_path.write_text(
            json.dumps(
                {
                    "SchemaVersion": 2,
                    "ArtifactName": ".",
                    "ArtifactType": "filesystem",
                    "Results": [result],
                }
            ),
            encoding="utf-8",
        )
        return raw_path

    def test_secret_detections_fail_and_report_only_counts(self) -> None:
        raw_path = self.write_scan(
            "trivy.json",
            secrets=[
                {
                    "RuleID": "generic-secret",
                    "StartLine": 42,
                    "Match": "synthetic-token-that-must-not-appear",
                }
            ],
        )

        report = create_security_report(raw_path, scan_outcome="success")
        rendered = json.dumps(report) + render_summary(report)

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["evidence"]["secrets_detected"], 1)
        self.assertEqual(
            report["evidence"]["secret_findings"],
            [{"rule_id": "generic-secret", "target": "tests/fixture.txt", "count": 1}],
        )
        self.assertIn("generic-secret", rendered)
        self.assertIn("tests/fixture.txt", rendered)
        self.assertIn("matched values and line numbers omitted", rendered)
        self.assertNotIn("synthetic-token-that-must-not-appear", rendered)
        self.assertNotIn("42", rendered)
        self.assertNotIn("Match", rendered)
        self.assertNotIn("StartLine", rendered)

    def test_unsafe_secret_target_is_redacted_from_diagnostics(self) -> None:
        unsafe_targets = (
            "../../private-marker/token.txt",
            "/private-marker/token.txt",
            r"C:\private-marker\token.txt",
            "folder/../../private-marker/token.txt",
            "folder\nprivate-marker/token.txt",
        )
        for index, target in enumerate(unsafe_targets):
            with self.subTest(target_kind=index):
                raw_path = self.write_scan(
                    "unsafe-target.json",
                    secrets=[{"RuleID": "generic-secret", "Match": "synthetic-marker"}],
                    target=target,
                )

                report = create_security_report(raw_path, scan_outcome="success")

                self.assertEqual(report["evidence"]["secret_findings"][0]["target"], "redacted")
                self.assertNotIn("private-marker", json.dumps(report))

    def test_relative_windows_secret_target_is_normalized(self) -> None:
        raw_path = self.write_scan(
            "windows-target.json",
            secrets=[{"RuleID": "generic-secret", "Match": "synthetic-marker"}],
            target=r".\tests\fixture.txt",
        )

        report = create_security_report(raw_path, scan_outcome="success")

        self.assertEqual(report["evidence"]["secret_findings"][0]["target"], "tests/fixture.txt")

    def test_secret_findings_are_aggregated_sorted_and_bounded(self) -> None:
        secrets = [{"RuleID": f"generic-secret-{index:02d}"} for index in range(21)]
        secrets.append({"RuleID": "generic-secret-00"})
        raw_path = self.write_scan("many-secrets.json", secrets=secrets)

        report = create_security_report(raw_path, scan_outcome="success")
        findings = report["evidence"]["secret_findings"]

        self.assertEqual(report["evidence"]["secrets_detected"], 22)
        self.assertEqual(len(findings), 20)
        self.assertEqual(findings[0]["rule_id"], "generic-secret-00")
        self.assertEqual(findings[0]["count"], 2)
        self.assertEqual(findings[-1]["rule_id"], "generic-secret-19")
        self.assertTrue(report["evidence"]["secret_findings_truncated"])
        self.assertIn("Additional secret finding locations were omitted", render_summary(report))

    def test_invalid_secret_rule_id_is_replaced_with_unknown(self) -> None:
        raw_path = self.write_scan(
            "invalid-rule.json",
            secrets=[{"RuleID": {"private-marker": "value"}, "Match": "synthetic-marker"}],
        )

        report = create_security_report(raw_path, scan_outcome="success")

        self.assertEqual(report["evidence"]["secret_findings"][0]["rule_id"], "unknown")
        self.assertNotIn("private-marker", json.dumps(report))

    def test_cli_writes_only_sanitized_report_and_summary(self) -> None:
        raw_path = self.write_scan(
            "trivy.json",
            secrets=[{"StartLine": 9876, "Match": "synthetic-token-never-to-be-published"}],
        )
        report_path = self.directory / "security-report.json"
        summary_path = self.directory / "summary.md"

        exit_code = main(
            [
                "--input",
                str(raw_path),
                "--scan-outcome",
                "success",
                "--report",
                str(report_path),
                "--summary",
                str(summary_path),
            ]
        )
        output = report_path.read_text(encoding="utf-8") + summary_path.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 1)
        self.assertNotIn("synthetic-token-never-to-be-published", output)
        self.assertNotIn("9876", output)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["schema"], "security-report/v1")

    def test_high_and_critical_vulnerabilities_fail(self) -> None:
        raw_path = self.write_scan(
            "trivy.json",
            vulnerabilities=[
                {
                    "Severity": "HIGH",
                    "VulnerabilityID": "CVE-2099-0001",
                    "PkgName": "fixture-package",
                },
                {
                    "Severity": "CRITICAL",
                    "VulnerabilityID": "CVE-2099-0002",
                    "PkgName": "fixture-package",
                },
            ],
        )

        report = create_security_report(raw_path, scan_outcome="success")

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["evidence"]["vulnerabilities"]["high"], 1)
        self.assertEqual(report["evidence"]["vulnerabilities"]["critical"], 1)
        self.assertEqual(report["code"], "SECURITY.HIGH_OR_CRITICAL_VULNERABILITY")

    def test_medium_and_low_vulnerabilities_are_advisories(self) -> None:
        raw_path = self.write_scan(
            "trivy.json",
            vulnerabilities=[
                {
                    "Severity": "MEDIUM",
                    "VulnerabilityID": "CVE-2099-0003",
                    "PkgName": "fixture-package",
                },
                {
                    "Severity": "LOW",
                    "VulnerabilityID": "CVE-2099-0004",
                    "PkgName": "fixture-package",
                },
                {
                    "Severity": "UNKNOWN",
                    "VulnerabilityID": "TEST-UNKNOWN-1",
                    "PkgName": "fixture-package",
                },
            ],
        )

        report = create_security_report(raw_path, scan_outcome="success")

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["evidence"]["vulnerabilities"]["medium"], 1)
        self.assertEqual(report["evidence"]["vulnerabilities"]["low"], 1)
        self.assertEqual(report["evidence"]["vulnerabilities"]["unknown"], 1)
        self.assertTrue(report["evidence"]["advisories"])
        self.assertEqual(len(report["evidence"]["advisories"]), 3)
        self.assertFalse(report["evidence"]["blocking_vulnerabilities"])

    def test_failed_scanner_does_not_trust_existing_output(self) -> None:
        raw_path = self.write_scan(
            "trivy.json",
            vulnerabilities=[{"Severity": "LOW"}],
        )

        report = create_security_report(raw_path, scan_outcome="failure")

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["code"], "SECURITY.SCANNER_FAILED")
        self.assertEqual(report["evidence"]["scanner_status"], "failed")
        self.assertFalse(report["evidence"]["advisories"])

    def test_malformed_output_missing_output_and_not_run_fail_closed(self) -> None:
        malformed_path = self.directory / "malformed.json"
        malformed_path.write_text("{not json", encoding="utf-8")

        malformed = create_security_report(malformed_path, scan_outcome="success")
        missing = create_security_report(self.directory / "missing.json", scan_outcome="success")
        not_run = create_security_report(self.directory / "not-run.json", scan_outcome="skipped")

        self.assertEqual(malformed["status"], "not_verified")
        self.assertEqual(malformed["code"], "SECURITY.SCAN_OUTPUT_INVALID")
        self.assertEqual(missing["status"], "not_verified")
        self.assertEqual(missing["code"], "SECURITY.SCAN_OUTPUT_INVALID")
        self.assertEqual(not_run["status"], "not_verified")
        self.assertEqual(not_run["code"], "SECURITY.SCAN_NOT_VERIFIED")

    def test_trivy_null_results_representation_is_a_valid_empty_scan(self) -> None:
        raw_path = self.directory / "empty-trivy.json"
        raw_path.write_text(
            json.dumps(
                {
                    "SchemaVersion": 2,
                    "ArtifactName": "/scan",
                    "ArtifactType": "filesystem",
                    "Results": None,
                }
            ),
            encoding="utf-8",
        )

        report = create_security_report(raw_path, scan_outcome="success")

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["evidence"]["secrets_detected"], 0)

    def test_trivy_omitted_results_representation_is_a_valid_empty_scan(self) -> None:
        raw_path = self.directory / "empty-trivy-omitted-results.json"
        raw_path.write_text(
            json.dumps(
                {
                    "SchemaVersion": 2,
                    "ArtifactName": ".",
                    "ArtifactType": "repository",
                }
            ),
            encoding="utf-8",
        )

        report = create_security_report(raw_path, scan_outcome="success")

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["evidence"]["output_validation"], "valid")
        self.assertEqual(report["evidence"]["secrets_detected"], 0)
        self.assertFalse(report["evidence"]["blocking_vulnerabilities"])
        self.assertFalse(report["evidence"]["advisories"])

    def test_trivy_non_list_results_representation_remains_not_verified(self) -> None:
        raw_path = self.directory / "invalid-trivy-results.json"
        raw_path.write_text(
            json.dumps(
                {
                    "SchemaVersion": 2,
                    "ArtifactName": ".",
                    "ArtifactType": "repository",
                    "Results": "not-a-list",
                }
            ),
            encoding="utf-8",
        )

        report = create_security_report(raw_path, scan_outcome="success")

        self.assertEqual(report["status"], "not_verified")
        self.assertEqual(report["code"], "SECURITY.SCAN_OUTPUT_INVALID")
        self.assertEqual(report["evidence"]["output_validation"], "results_invalid")

    def test_trivy_repository_artifact_type_is_valid_for_git_checkout_scans(self) -> None:
        raw_path = self.write_scan("repository.json", secrets=[], vulnerabilities=[])
        document = json.loads(raw_path.read_text(encoding="utf-8"))
        document["ArtifactType"] = "repository"
        raw_path.write_text(json.dumps(document), encoding="utf-8")

        report = create_security_report(raw_path, scan_outcome="success")

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["evidence"]["output_validation"], "valid")

    def test_unhashable_artifact_types_fail_closed_with_sanitized_reason(self) -> None:
        for artifact_type in ([], {}):
            with self.subTest(artifact_type=type(artifact_type).__name__):
                raw_path = self.write_scan("invalid-type.json", secrets=[], vulnerabilities=[])
                document = json.loads(raw_path.read_text(encoding="utf-8"))
                document["ArtifactType"] = artifact_type
                raw_path.write_text(json.dumps(document), encoding="utf-8")

                report = create_security_report(raw_path, scan_outcome="success")

                self.assertEqual(report["status"], "not_verified")
                self.assertEqual(report["evidence"]["output_validation"], "artifact_type_invalid")

    def test_incomplete_trivy_document_without_schema_version_is_not_verified(self) -> None:
        incomplete_path = self.directory / "incomplete.json"
        incomplete_path.write_text(
            json.dumps({"SchemaVersion": 2, "Results": []}), encoding="utf-8"
        )

        report = create_security_report(incomplete_path, scan_outcome="success")

        self.assertEqual(report["status"], "not_verified")

    def test_invalid_scan_reports_safe_validation_reason(self) -> None:
        raw_path = self.directory / "invalid-envelope.json"
        raw_path.write_text(
            json.dumps(
                {
                    "SchemaVersion": 2,
                    "Results": [],
                    "SyntheticSecretMarker": "do-not-report-this-value",
                }
            ),
            encoding="utf-8",
        )

        report = create_security_report(raw_path, scan_outcome="success")
        rendered = json.dumps(report) + render_summary(report)

        self.assertEqual(report["evidence"]["output_validation"], "artifact_name_invalid")
        self.assertNotIn("do-not-report-this-value", rendered)

    def test_report_uses_the_shared_diagnostic_contract_fields(self) -> None:
        raw_path = self.write_scan("trivy.json", secrets=[])
        report = create_security_report(raw_path, scan_outcome="success")

        self.assertEqual(
            set(report),
            {
                "schema",
                "service",
                "version",
                "phase",
                "status",
                "code",
                "cause_status",
                "evidence",
                "possible_causes",
                "recommended_actions",
            },
        )
        self.assertEqual(
            set(report["evidence"]),
            {
                "scanner",
                "scanner_status",
                "output_validation",
                "secret_scanner_self_test",
                "secrets_detected",
                "secret_findings",
                "secret_findings_truncated",
                "vulnerabilities",
                "blocking_vulnerabilities",
                "advisories",
            },
        )
        self.assertEqual(report["evidence"]["secret_scanner_self_test"], "not_applicable")


if __name__ == "__main__":
    unittest.main()
