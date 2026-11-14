"""Prove the incremental lint and type gates reject a newly added bad file."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def test_incremental_gates_detect_an_added_file_with_lint_and_type_errors(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "quality-gate-repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.name", "Quality Gate Test")
    _git(repository, "config", "user.email", "quality-gate@example.invalid")

    (repository / "baseline.py").write_text(
        "def baseline() -> int:\n    return 1\n", encoding="utf-8"
    )
    _git(repository, "add", "baseline.py")
    _git(repository, "commit", "--quiet", "-m", "test: establish baseline")
    baseline = _git(repository, "rev-parse", "HEAD")

    (repository / "new_bad.py").write_text(
        "import os\n\ndef wrong_type(value: str) -> int:\n    return value\n",
        encoding="utf-8",
    )
    _git(repository, "add", "new_bad.py")
    _git(repository, "commit", "--quiet", "-m", "test: add invalid Python")

    changed = (
        subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                "-z",
                "--diff-filter=ACMRT",
                f"{baseline}...HEAD",
                "--",
                "*.py",
            ],
            cwd=repository,
            capture_output=True,
            check=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    changed_files = [name for name in changed if name]
    assert changed_files == ["new_bad.py"]

    lint = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--config",
            str(ROOT / "pyproject.toml"),
            *changed_files,
        ],
        cwd=repository,
        capture_output=True,
        check=False,
        text=True,
    )
    typing = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyright",
            "--project",
            str(ROOT / "pyproject.toml"),
            *[str(repository / name) for name in changed_files],
        ],
        cwd=repository,
        capture_output=True,
        check=False,
        text=True,
    )

    assert lint.returncode != 0
    assert "F401" in lint.stdout + lint.stderr
    assert typing.returncode != 0
    assert "error" in (typing.stdout + typing.stderr).lower()
