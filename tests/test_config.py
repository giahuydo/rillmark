"""Offline configuration contract checks."""

import json
from pathlib import Path

import pytest

from rillmark.config import load_config
from rillmark.errors import ConfigError


def selection_file(tmp_path: Path, **changes: object) -> Path:
    """Write a minimal non-secret selection file."""
    path = tmp_path / "selection.json"
    data = {"section_ids": [10, 20], "youtube_article_id": 99, "min_articles": 30}
    data.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_config_defaults_allow_dry_run_without_key(tmp_path: Path) -> None:
    path = selection_file(tmp_path)
    config = load_config({}, path)
    assert config.api_key is None
    assert config.vector_store_id is None
    assert config.selection.section_ids == (10, 20)
    assert config.chunk.max_tokens == 4096
    assert config.chunk.overlap_tokens == 0
    assert config.zendesk_base_url == "https://support.optisigns.com"
    assert config.gist_id is None
    assert config.gist_token is None


def test_config_env_precedence_and_overrides(tmp_path: Path) -> None:
    path = selection_file(tmp_path)
    config = load_config(
        {
            "API_KEY": "primary",
            "OPENAI_API_KEY": "fallback",
            "VECTOR_STORE_ID": "vs_test",
            "SECTION_IDS": "30, 40",
            "YOUTUBE_ARTICLE_ID": "42",
            "ZENDESK_BASE_URL": "https://example.org/",
            "MAX_CHUNK_SIZE_TOKENS": "800",
            "CHUNK_OVERLAP_TOKENS": "400",
            "ARTIFACT_GIST_ID": "gist-test",
            "ARTIFACT_GITHUB_TOKEN": "token-test",
        },
        path,
    )
    assert config.api_key == "primary"
    assert config.vector_store_id == "vs_test"
    assert config.selection.section_ids == (30, 40)
    assert config.selection.youtube_article_id == 42
    assert config.selection.min_articles == 30
    assert (config.chunk.max_tokens, config.chunk.overlap_tokens) == (800, 400)
    assert config.zendesk_base_url == "https://example.org"
    assert (config.gist_id, config.gist_token) == ("gist-test", "token-test")


def test_config_fallback_key_when_primary_missing(tmp_path: Path) -> None:
    assert load_config({"OPENAI_API_KEY": "fallback"}, selection_file(tmp_path)).api_key == (
        "fallback"
    )


@pytest.mark.parametrize(
    "env",
    [
        {"MAX_CHUNK_SIZE_TOKENS": "99"},
        {"MAX_CHUNK_SIZE_TOKENS": "4097"},
        {"MAX_CHUNK_SIZE_TOKENS": "n/a"},
        {"MAX_CHUNK_SIZE_TOKENS": "800", "CHUNK_OVERLAP_TOKENS": "401"},
        {"CHUNK_OVERLAP_TOKENS": "-1"},
        {"SECTION_IDS": "1,,2"},
        {"YOUTUBE_ARTICLE_ID": "bad"},
        {"API_KEY": "secret-value", "SECTION_IDS": "secret-value"},
    ],
)
def test_config_invalid_env_is_actionable_and_never_leaks_secrets(
    tmp_path: Path, env: dict[str, str]
) -> None:
    with pytest.raises(ConfigError) as exc:
        load_config(env, selection_file(tmp_path))
    assert "secret-value" not in str(exc.value)
    assert str(exc.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"min_articles": 29},
        {"section_ids": []},
        {"section_ids": [10, 10]},
        {"youtube_article_id": "bad"},
    ],
)
def test_config_rejects_invalid_selection(tmp_path: Path, changes: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        load_config({}, selection_file(tmp_path, **changes))


def test_config_rejects_missing_or_invalid_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config({}, tmp_path / "missing.json")
    path = tmp_path / "selection.json"
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config({}, path)
