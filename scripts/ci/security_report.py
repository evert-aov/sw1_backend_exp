"""Create a sanitized, cross-project CI security report from Trivy JSON."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "security-report/v1"
SERVICE = "backend"
SEVERITIES = ("critical", "high", "medium", "low", "unknown")
VALID_ARTIFACT_TYPES = {"filesystem", "repository"}
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9@._/+:-]{1,200}$")
SECRET_RULE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
SECRET_TARGET_PATTERN = re.compile(r"^[A-Za-z0-9._ @+/-]{1,240}$")
MAX_SECRET_FINDINGS = 20


def _safe_version(value: str | None) -> str:
    if value and VERSION_PATTERN.fullmatch(value):
        return value
    return "unknown"


def _safe_secret_rule_id(value: Any) -> str:
    if isinstance(value, str) and SECRET_RULE_ID_PATTERN.fullmatch(value):
        return value
    return "unknown"


def _safe_secret_target(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 240 or value != value.strip():
        return "redacted"
    target = value.replace("\\", "/")
    while target.startswith("./"):
        target = target[2:]
    if (
        not SECRET_TARGET_PATTERN.fullmatch(target)
        or target.startswith("/")
        or any(segment in ("", ".", "..") for segment in target.split("/"))
    ):
        return "redacted"
    return target


def _empty_evidence(scanner_status: str, output_validation: str = "not_checked") -> dict[str, Any]:
    return {
        "scanner": "Trivy filesystem",
        "scanner_status": scanner_status,
        "output_validation": output_validation,
        "secret_scanner_self_test": "not_applicable",
        "secrets_detected": 0,
        "secret_findings": [],
        "secret_findings_truncated": False,
        "vulnerabilities": {severity: 0 for severity in SEVERITIES},
        "blocking_vulnerabilities": [],
        "advisories": [],
    }


def _report(
    *,
    status: str,
    code: str,
    cause_status: str,
    evidence: dict[str, Any],
    version: str | None,
    possible_causes: list[str] | None = None,
    recommended_actions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "service": SERVICE,
        "version": _safe_version(version),
        "phase": "security_scan",
        "status": status,
        "code": code,
        "cause_status": cause_status,
        "evidence": evidence,
        "possible_causes": possible_causes or [],
        "recommended_actions": recommended_actions or [],
    }


def _not_verified(
    *,
    scanner_status: str,
    code: str,
    version: str | None,
    output_validation: str,
) -> dict[str, Any]:
    return _report(
        status="not_verified",
        code=code,
        cause_status="unknown",
        evidence=_empty_evidence(scanner_status, output_validation),
        version=version,
        possible_causes=[
            "The scanner may have failed, been skipped, or produced an invalid report."
        ],
        recommended_actions=[
            "Inspect the Trivy step outcome and rerun the filesystem security scan."
        ],
    )


def _envelope_validation_error(document: Any) -> str | None:
    if not isinstance(document, dict):
        return "root_not_object"
    if document.get("SchemaVersion") != 2:
        return "unsupported_schema_version"
    if not isinstance(document.get("ArtifactName"), str) or not document["ArtifactName"]:
        return "artifact_name_invalid"
    artifact_type = document.get("ArtifactType")
    if not isinstance(artifact_type, str) or artifact_type not in VALID_ARTIFACT_TYPES:
        return "artifact_type_invalid"
    results = document.get("Results")
    if results is not None and not isinstance(results, list):
        return "results_invalid"
    return None


def _finding_validation_error(error: ValueError) -> str:
    return {
        "invalid result structure": "result_not_object",
        "invalid finding collection": "findings_not_collection",
        "invalid secret finding": "secret_not_object",
        "invalid vulnerability finding": "vulnerability_not_object",
        "invalid vulnerability metadata": "vulnerability_metadata_invalid",
    }.get(str(error), "finding_invalid")


def _scan_findings(document: dict[str, Any]) -> dict[str, Any]:
    counts = {severity: 0 for severity in SEVERITIES}
    secrets_detected = 0
    secret_finding_counts: dict[tuple[str, str], int] = {}
    blocking_vulnerabilities: list[dict[str, str]] = []
    advisories: list[dict[str, str]] = []

    # Trivy omits Results when its report has no findings (the Go field is omitempty).
    for result in document.get("Results") or []:
        if not isinstance(result, dict):
            raise ValueError("invalid result structure")

        secrets = result.get("Secrets")
        vulnerabilities = result.get("Vulnerabilities")
        if secrets is None:
            secrets = []
        if vulnerabilities is None:
            vulnerabilities = []
        if not isinstance(secrets, list) or not isinstance(vulnerabilities, list):
            raise ValueError("invalid finding collection")
        if any(not isinstance(secret, dict) for secret in secrets):
            raise ValueError("invalid secret finding")
        secrets_detected += len(secrets)
        target = _safe_secret_target(result.get("Target"))
        for secret in secrets:
            key = (_safe_secret_rule_id(secret.get("RuleID")), target)
            secret_finding_counts[key] = secret_finding_counts.get(key, 0) + 1

        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                raise ValueError("invalid vulnerability finding")
            severity = vulnerability.get("Severity")
            identifier = vulnerability.get("VulnerabilityID")
            package = vulnerability.get("PkgName")
            if (
                not isinstance(severity, str)
                or severity.lower() not in counts
                or not isinstance(identifier, str)
                or not IDENTIFIER_PATTERN.fullmatch(identifier)
                or not isinstance(package, str)
                or not PACKAGE_PATTERN.fullmatch(package)
            ):
                raise ValueError("invalid vulnerability metadata")

            normalized_severity = severity.lower()
            counts[normalized_severity] += 1
            finding = {
                "severity": normalized_severity.upper(),
                "id": identifier,
                "package_name": package,
            }
            if normalized_severity in ("critical", "high"):
                blocking_vulnerabilities.append(finding)
            else:
                advisories.append(finding)

    sorted_secret_findings = [
        {"rule_id": rule_id, "target": target, "count": count}
        for (rule_id, target), count in sorted(secret_finding_counts.items())
    ]
    return {
        "secrets_detected": secrets_detected,
        "secret_findings": sorted_secret_findings[:MAX_SECRET_FINDINGS],
        "secret_findings_truncated": len(sorted_secret_findings) > MAX_SECRET_FINDINGS,
        "vulnerabilities": counts,
        "blocking_vulnerabilities": blocking_vulnerabilities,
        "advisories": advisories,
    }


def create_security_report(
    raw_path: Path, *, scan_outcome: str, version: str | None = None
) -> dict[str, Any]:
    """Build the shared report contract without copying secret matches or lines."""
    if scan_outcome != "success":
        failed = scan_outcome in ("failure", "cancelled")
        return _report(
            status="failed" if failed else "not_verified",
            code="SECURITY.SCANNER_FAILED" if failed else "SECURITY.SCAN_NOT_VERIFIED",
            cause_status="unknown",
            evidence=_empty_evidence("failed" if failed else "not_run"),
            version=version,
            possible_causes=["The Trivy action did not complete a verified filesystem scan."],
            recommended_actions=[
                "Inspect the scanner step and rerun the filesystem security scan."
            ],
        )

    try:
        raw_json = raw_path.read_text(encoding="utf-8")
    except OSError:
        return _not_verified(
            scanner_status="invalid_output",
            code="SECURITY.SCAN_OUTPUT_INVALID",
            version=version,
            output_validation="input_unavailable",
        )
    except UnicodeDecodeError:
        return _not_verified(
            scanner_status="invalid_output",
            code="SECURITY.SCAN_OUTPUT_INVALID",
            version=version,
            output_validation="invalid_encoding",
        )

    try:
        document = json.loads(raw_json)
    except json.JSONDecodeError:
        return _not_verified(
            scanner_status="invalid_output",
            code="SECURITY.SCAN_OUTPUT_INVALID",
            version=version,
            output_validation="invalid_json",
        )

    envelope_error = _envelope_validation_error(document)
    if envelope_error:
        return _not_verified(
            scanner_status="invalid_output",
            code="SECURITY.SCAN_OUTPUT_INVALID",
            version=version,
            output_validation=envelope_error,
        )

    try:
        findings = _scan_findings(document)
    except ValueError as error:
        return _not_verified(
            scanner_status="invalid_output",
            code="SECURITY.SCAN_OUTPUT_INVALID",
            version=version,
            output_validation=_finding_validation_error(error),
        )

    evidence = _empty_evidence("completed", "valid")
    evidence.update(findings)
    secret_detected = findings["secrets_detected"] > 0
    high_vulnerability = bool(
        findings["vulnerabilities"]["critical"] or findings["vulnerabilities"]["high"]
    )
    if secret_detected or high_vulnerability:
        actions = []
        if secret_detected:
            actions.append("Remove or rotate exposed credentials, then rerun the scan.")
        if high_vulnerability:
            actions.append("Upgrade or mitigate the HIGH and CRITICAL vulnerable packages.")
        return _report(
            status="failed",
            code=(
                "SECURITY.SECRET_DETECTED"
                if secret_detected
                else "SECURITY.HIGH_OR_CRITICAL_VULNERABILITY"
            ),
            cause_status="confirmed",
            evidence=evidence,
            version=version,
            recommended_actions=actions,
        )

    has_advisories = bool(findings["advisories"])
    return _report(
        status="passed",
        code="SECURITY.SCAN_ADVISORIES" if has_advisories else "SECURITY.SCAN_PASSED",
        cause_status="unknown",
        evidence=evidence,
        version=version,
        recommended_actions=(
            ["Review the lower-severity vulnerability advisories and plan remediation."]
            if has_advisories
            else ["No blocking filesystem security findings were detected."]
        ),
    )


def render_summary(report: dict[str, Any]) -> str:
    """Render only validated finding identifiers and package names."""
    evidence = report["evidence"]
    vulnerabilities = evidence["vulnerabilities"]
    lines = [
        "## Filesystem security scan",
        f"- Status: **{report['status']}** (`{report['code']}`)",
        f"- Scanner status: `{evidence['scanner_status']}`",
        f"- Output validation: `{evidence['output_validation']}`",
        f"- Secret findings: {evidence['secrets_detected']}",
        "- Vulnerabilities: "
        + ", ".join(f"{severity.upper()} {vulnerabilities[severity]}" for severity in SEVERITIES),
    ]
    if evidence["secret_findings"]:
        lines.append("- Secret finding locations (matched values and line numbers omitted):")
        lines.extend(
            f"  - `{item['rule_id']}` in `{item['target']}` (count: {item['count']})"
            for item in evidence["secret_findings"]
        )
        if evidence["secret_findings_truncated"]:
            lines.append(
                "  - Additional secret finding locations were omitted by the report limit."
            )
    for heading, key in (
        ("Blocking HIGH/CRITICAL vulnerabilities", "blocking_vulnerabilities"),
        ("Lower-severity advisories", "advisories"),
    ):
        findings = evidence[key]
        if findings:
            lines.append(f"- {heading}:")
            lines.extend(
                f"  - {item['severity']} {item['id']} in {item['package_name']}"
                for item in findings
            )
    lines.extend(f"- Recommended action: {action}" for action in report["recommended_actions"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--scan-outcome", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args(argv)

    report = create_security_report(
        args.input,
        scan_outcome=args.scan_outcome,
        version=os.environ.get("GITHUB_SHA"),
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with args.summary.open("a", encoding="utf-8") as summary_file:
        summary_file.write(render_summary(report))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
