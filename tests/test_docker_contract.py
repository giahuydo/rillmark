"""Offline checks for the one-shot Docker runtime and its build context."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def docker_instructions() -> list[tuple[str, str]]:
    """Return non-comment Dockerfile instructions as keyword/value pairs."""
    lines = (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    return [
        (keyword.upper(), value.strip())
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
        for keyword, _, value in [line.strip().partition(" ")]
    ]


def test_image_uses_slim_python_and_pinned_runtime_requirements() -> None:
    """Require a single Python runtime stage and only pinned runtime packages."""
    instructions = docker_instructions()
    assert [value for keyword, value in instructions if keyword == "FROM"] == ["python:3.12-slim"]
    assert ("WORKDIR", "/app") in instructions
    runs = [value for keyword, value in instructions if keyword == "RUN"]
    assert any(re.search(r"\bpip\s+install\b.*\s-r\s+requirements\.txt\b", run) for run in runs)
    assert not any("requirements-dev" in value for _, value in instructions)
    assert all(
        re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*==[^\s#]+", line.strip())
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )


def test_image_has_non_root_user_and_exec_form_entrypoint() -> None:
    """Require an unprivileged final user and deterministic Docker argv."""
    instructions = docker_instructions()
    assert any(
        keyword == "RUN" and re.search(r"\b(useradd|adduser)\b", value)
        for keyword, value in instructions
    )
    assert instructions[-3:] == [
        ("USER", "app"),
        ("ENTRYPOINT", '["python"]'),
        ("CMD", '["main.py"]'),
    ]
    for keyword, expected in (("ENTRYPOINT", ["python"]), ("CMD", ["main.py"])):
        values = [value for name, value in instructions if name == keyword]
        assert len(values) == 1
        assert json.loads(values[0]) == expected


def test_image_copies_app_and_versioned_selection() -> None:
    """Require explicit runtime input copies, including the default selection."""
    copies = [
        value.removeprefix("--chown=app:app ")
        for keyword, value in docker_instructions()
        if keyword == "COPY"
    ]
    assert set(copies) == {
        "requirements.txt ./",
        "main.py ./",
        "rillmark/ ./rillmark/",
        "config/selection.json ./config/selection.json",
    }
    assert len(copies) == 4
    assert (ROOT / "config/selection.json").is_file()


def test_build_context_excludes_private_and_transient_files() -> None:
    """Keep credentials, tests, raw research, outputs and agent metadata out."""
    patterns = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert {
        ".git",
        ".gitignore",
        ".env*",
        "research/",
        "tests/",
        "out/",
        "last_run.json",
        "**/__pycache__/",
        "**/*.py[cod]",
        ".pytest_cache/",
        ".ruff_cache/",
        ".agents/",
        ".claude/",
        ".pi/",
        "*.swp",
        ".DS_Store",
    } <= patterns
    assert not any(pattern.startswith("!config/") for pattern in patterns)
