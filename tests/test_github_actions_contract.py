"""Offline static checks for the optional GitHub Actions scheduler contract."""

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/rillmark-daily.yml"


def _workflow() -> str:
    """Read the workflow without importing YAML or contacting GitHub."""
    return WORKFLOW.read_text(encoding="utf-8")


def _step(name: str) -> str:
    """Return one named step's text for checks that must not match other steps."""
    match = re.search(
        rf"(?ms)^      - name: {re.escape(name)}\n(.*?)(?=^      - name: |\Z)", _workflow()
    )
    assert match is not None, f"missing step: {name}"
    return match.group(1)


def test_schedule_and_dispatch_default_to_safe_dry_run() -> None:
    text = _workflow()
    assert re.search(r'(?m)^    - cron: ["\']0 3 \* \* \*["\']$', text)
    assert re.search(r"(?m)^  workflow_dispatch:\s*$", text)
    assert re.search(r"(?m)^        default: dry-run\s*$", text)
    assert re.search(r"(?m)^          - dry-run\s*$", text)
    assert re.search(r"(?m)^          - sync\s*$", text)
    dry = _step("Dry run")
    assert "github.event_name == 'workflow_dispatch'" in dry
    assert "inputs.mode == 'dry-run'" in dry
    assert "python main.py --dry-run" in dry
    assert "API_KEY:" not in dry
    assert "OPENAI_API_KEY" not in dry


def test_schedule_is_opt_in_and_manual_sync_explicit() -> None:
    text = _workflow()
    assert re.search(
        r"(?m)^    if:.*github.event_name == 'schedule'.*vars.RILLMARK_SCHEDULE_ENABLED == 'true'",
        text,
    )
    live = _step("Live sync")
    assert "github.event_name == 'schedule'" in live
    assert "inputs.mode == 'sync'" in live
    assert re.search(r"(?m)^        run: python main.py\s*$", live)
    assert "--dry-run" not in live


def test_least_privilege_and_bounded_execution() -> None:
    text = _workflow()
    assert re.search(r"(?m)^permissions:\n  contents: read\s*$", text)
    assert "contents: write" not in text
    assert "group: rillmark-sync" in text
    assert "cancel-in-progress: false" in text
    assert "timeout-minutes: 20" in text
    assert "runs-on: ubuntu-latest" in text
    assert re.search(r"uses: actions/checkout@v\d+", text)
    assert re.search(r"uses: actions/setup-python@v\d+", text)
    assert 'python-version: "3.12"' in text
    assert "pip install -r requirements.txt" in text
    assert "requirements-dev.txt" not in text


def test_live_sync_requires_gist_and_maps_only_intended_credentials() -> None:
    live = _step("Live sync")
    assert "API_KEY: ${{ secrets.OPENAI_API_KEY }}" in live
    assert "ARTIFACT_GITHUB_TOKEN: ${{ secrets.ARTIFACT_GITHUB_TOKEN }}" in live
    assert "ARTIFACT_GIST_ID: ${{ vars.ARTIFACT_GIST_ID }}" in live
    assert "VECTOR_STORE_ID: ${{ vars.VECTOR_STORE_ID }}" in live
    assert "REQUIRE_PUBLISH: 'true'" in live
    text = _workflow()
    assert "secrets.GITHUB_TOKEN" not in text
    assert "github.token" not in text
    assert not re.search(r"(?im)^\s*run:\s*(?:echo|printenv|env)\b", text)
    assert not re.search(r"(?i)\becho\b[^\n]*\$\{\{\s*secrets\.", text)
    assert ".env" not in text


def test_report_upload_runs_even_on_failure() -> None:
    artifact = _step("Upload redacted run artifact")
    assert "uses: actions/upload-artifact@" in artifact
    assert "if: ${{ always() }}" in artifact
    assert re.search(r"(?m)^          path: last_run.json\s*$", artifact)
