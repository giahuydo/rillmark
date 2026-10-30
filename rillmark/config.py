"""Validate versioned selection and environment configuration without reading global state."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from rillmark.errors import ConfigError
from rillmark.models import ChunkConfig, Selection

DEFAULT_BASE_URL = "https://support.optisigns.com"


@dataclass(frozen=True, slots=True)
class Config:
    """Validated settings for a single run; the API key is optional for dry runs."""

    api_key: str | None
    vector_store_id: str | None
    selection: Selection
    chunk: ChunkConfig
    zendesk_base_url: str
    gist_id: str | None
    gist_token: str | None


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ConfigError(f"{name} must be a positive integer")
    try:
        number = int(value)
    except ValueError:
        raise ConfigError(f"{name} must be a positive integer") from None
    if number <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return number


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ConfigError(f"{name} must be a nonnegative integer")
    try:
        number = int(value)
    except ValueError:
        raise ConfigError(f"{name} must be a nonnegative integer") from None
    if number < 0:
        raise ConfigError(f"{name} must be a nonnegative integer")
    return number


def _selection_data(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigError("Cannot read valid JSON from config/selection.json") from exc
    if not isinstance(data, dict):
        raise ConfigError("config/selection.json must contain a JSON object")
    return data


def _selection(env: Mapping[str, str], path: Path) -> Selection:
    data = _selection_data(path)
    raw_sections = data.get("section_ids")
    if "SECTION_IDS" in env:
        raw_sections = env["SECTION_IDS"].split(",")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ConfigError("SECTION_IDS / section_ids must contain at least one section ID")
    section_ids = tuple(_positive_int(value, "SECTION_IDS / section_ids") for value in raw_sections)
    if len(section_ids) != len(set(section_ids)):
        raise ConfigError("SECTION_IDS / section_ids must not contain duplicates")
    youtube_id = _positive_int(
        env.get("YOUTUBE_ARTICLE_ID", data.get("youtube_article_id")), "YOUTUBE_ARTICLE_ID"
    )
    min_articles = _positive_int(data.get("min_articles"), "min_articles")
    if min_articles < 30:
        raise ConfigError("min_articles must be at least 30")
    return Selection(section_ids, youtube_id, min_articles)


def load_config(env: Mapping[str, str], selection_path: Path) -> Config:
    """Return a frozen validated config from supplied env and versioned selection JSON."""
    selection = _selection(env, selection_path)
    max_tokens = _positive_int(env.get("MAX_CHUNK_SIZE_TOKENS", 4096), "MAX_CHUNK_SIZE_TOKENS")
    overlap = _nonnegative_int(env.get("CHUNK_OVERLAP_TOKENS", 0), "CHUNK_OVERLAP_TOKENS")
    if not 100 <= max_tokens <= 4096:
        raise ConfigError("MAX_CHUNK_SIZE_TOKENS must be between 100 and 4096")
    if overlap > max_tokens // 2:
        raise ConfigError("CHUNK_OVERLAP_TOKENS must be at most half MAX_CHUNK_SIZE_TOKENS")
    base_url = env.get("ZENDESK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    if not base_url.startswith("https://") or not base_url.removeprefix("https://"):
        raise ConfigError("ZENDESK_BASE_URL must be a valid HTTPS URL")
    return Config(
        api_key=env.get("API_KEY") or env.get("OPENAI_API_KEY") or None,
        vector_store_id=env.get("VECTOR_STORE_ID") or None,
        selection=selection,
        chunk=ChunkConfig(max_tokens, overlap),
        zendesk_base_url=base_url,
        gist_id=env.get("ARTIFACT_GIST_ID") or None,
        gist_token=env.get("ARTIFACT_GITHUB_TOKEN") or None,
    )
