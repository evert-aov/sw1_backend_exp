import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.core.diagnostics import ErrorCode

REPORT = Path(__file__).parents[1] / "infra/aws/deploy-report.py"
DEPLOY_SCRIPT = Path(__file__).parents[1] / "infra/aws/deploy-ec2.sh"


def report(phase, status, evidence=None):
    event = {
        "service": "experiencia-backend",
        "version": "abc123-42-1",
        "phase": phase,
        "status": status,
        "evidence": evidence or {},
    }
    result = subprocess.run(
        [sys.executable, str(REPORT)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_success_report_has_contract_and_does_not_claim_other_phases():
    value = report("readiness", "passed", {"probe": "health_ready", "attempt": 3})
    assert value["schema"] == "diagnostic-report/v1"
    assert value["service"] == "experiencia-backend"
    assert value["version"] == "abc123-42-1"
    assert value["phase"] == "readiness"
    assert value["status"] == "passed"
    assert value["cause_status"] == "unknown"
    assert value["code"] is None
    assert value["evidence"] == {"probe": "health_ready", "attempt": 3}
    assert value["recommended_actions"] == []


def test_failed_phase_classifies_known_failure_with_safe_cause_and_actions():
    value = report("startup", "failed", {"exit_code": 1, "exception_type": "ContainerStartError"})
    assert value["status"] == "failed"
    assert value["code"] == "DEPLOY.STARTUP_FAILED"
    assert value["code"] in {code.value for code in ErrorCode}
    assert value["cause_status"] == "hypothesis"
    assert value["possible_causes"]
    assert value["recommended_actions"]
    assert value["evidence"] == {"exit_code": 1, "exception_type": "ContainerStartError"}
    assert {
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
    } <= value.keys()


def test_untrusted_failure_text_and_secrets_are_redacted():
    value = report(
        "postdeploy",
        "failed",
        {
            "status_code": 500,
            "request_body": "private body",
            "command": "curl https://user:pass@example.test --header 'Authorization: Bearer secret'",
            "error": "traceback with secret",
            "token": "secret",
        },
    )
    rendered = json.dumps(value)
    assert value["code"] == "DEPLOY.POSTDEPLOY_FAILED"
    assert value["evidence"] == {"status_code": 500}
    for secret in ("private body", "user:pass", "Authorization", "secret", "traceback"):
        assert secret not in rendered


def test_not_verified_phase_is_not_reported_as_success():
    value = report("readiness", "not_verified")

    assert value["status"] == "not_verified"
    assert value["cause_status"] == "unknown"
    assert value["code"] is None
    assert value["recommended_actions"]


def test_invalid_phase_shapes_fail_closed_without_echoing_input():
    result = subprocess.run(
        [sys.executable, str(REPORT)],
        input=json.dumps({"phase": [], "status": "passed", "token": "synthetic-secret"}),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "synthetic-secret" not in result.stdout
    assert json.loads(result.stdout)["code"] == "DEPLOY.REPORT_INVALID"


def validate_root_contract(payload):
    return subprocess.run(
        [sys.executable, str(REPORT), "--validate-root-contract"],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )


def test_root_contract_validator_rejects_http_200_html_and_wrong_json():
    html = validate_root_contract("<html>wrong service</html>")
    wrong_json = validate_root_contract('{"status":"online","project":"other"}')

    assert html.returncode == 1
    assert wrong_json.returncode == 1
    assert html.stdout == html.stderr == ""
    assert wrong_json.stdout == wrong_json.stderr == ""


def test_root_contract_validator_accepts_the_existing_health_response_shape():
    result = validate_root_contract(
        '{"status":"online","project":"EXPERIENCIA API","version":"1.0.0"}'
    )

    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


def _fake_executable(path, contents):
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


def _run_deploy_with_root_response(tmp_path, root_response):
    project = tmp_path / "project"
    helper = project / "bin" / "deploy-report.py"
    helper.parent.mkdir(parents=True)
    shutil.copy2(REPORT, helper)
    (project / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    (project / "release.env").write_text("IMAGE_TAG=previous\n", encoding="utf-8")
    runtime_env = tmp_path / "runtime.env"
    runtime_env.write_text("ECR_REGISTRY=test.invalid\nAWS_REGION=test-1\n", encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _fake_executable(fake_bin / "aws", "#!/bin/sh\nprintf 'synthetic-password\\n'\n")
    _fake_executable(
        fake_bin / "docker",
        """#!/bin/sh
if [ "$1" = "login" ]; then cat >/dev/null; exit 0; fi
case "$*" in
  */health/ready*) exit 0 ;;
  *127.0.0.1:8000/*) printf '%s' "$ROOT_RESPONSE"; exit 0 ;;
esac
exit 0
""",
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
            "EXPERIENCIA_AWS_PROJECT_DIR": str(project),
            "EXPERIENCIA_AWS_RUNTIME_ENV_FILE": str(runtime_env),
            "ROOT_RESPONSE": root_response,
        }
    )
    return subprocess.run(
        ["bash", str(DEPLOY_SCRIPT), "release-test"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )


def _reports_from_deploy(result):
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]


def test_deploy_script_rejects_http_200_html_and_reports_confirmed_contract_failure(tmp_path):
    response_body = "<html>wrong service synthetic-body</html>"
    result = _run_deploy_with_root_response(tmp_path, response_body)

    reports = _reports_from_deploy(result)
    assert result.returncode != 0
    assert reports[-1]["phase"] == "postdeploy"
    assert reports[-1]["status"] == "failed"
    assert reports[-1]["code"] == "DEPLOY.POSTDEPLOY_FAILED"
    assert reports[-1]["cause_status"] == "confirmed"
    assert reports[-1]["evidence"]["probe"] == "root_contract"
    assert response_body not in result.stdout + result.stderr
    assert (tmp_path / "project" / "release.env").read_text() == "IMAGE_TAG=previous\n"


def test_deploy_script_reports_valid_root_contract_as_postdeploy_passed(tmp_path):
    response_body = '{"status":"online","project":"EXPERIENCIA API","version":"1.0.0"}'
    result = _run_deploy_with_root_response(tmp_path, response_body)

    reports = _reports_from_deploy(result)
    assert result.returncode == 0
    assert reports[-1]["phase"] == "postdeploy"
    assert reports[-1]["status"] == "passed"
    assert reports[-1]["evidence"]["probe"] == "root_contract"
