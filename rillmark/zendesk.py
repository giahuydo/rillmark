"""Thin Zendesk GET edge, complete pagination and deterministic selection."""

import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests

from rillmark.errors import FetchError, SelectionError
from rillmark.models import LOCALE, Article, Selection

MAX_ATTEMPTS = 3


def _retry_delay(value: str | None, attempt: int) -> float:
    if value:
        try:
            return min(30.0, max(0.0, float(value)))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                return min(30.0, max(0.0, (retry_at - datetime.now(UTC)).total_seconds()))
            except (TypeError, ValueError, OverflowError):
                pass
    return float(2 ** (attempt - 1))


def http_get_json(url: str) -> dict:
    """GET JSON with timeouts and up to three attempts for 429/5xx responses."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, timeout=(5, 30))
            if (
                response.status_code == 429 or 500 <= response.status_code <= 599
            ) and attempt < MAX_ATTEMPTS:
                time.sleep(_retry_delay(response.headers.get("Retry-After"), attempt))
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise FetchError("Zendesk returned a non-object JSON page")
            return payload
        except (requests.RequestException, ValueError) as exc:
            raise FetchError("Zendesk GET or JSON decoding failed") from exc
    raise FetchError("Zendesk GET failed after three attempts")


def _article(data: object) -> Article:
    if not isinstance(data, dict):
        raise FetchError("Zendesk page contains a malformed article")
    fields = ("id", "title", "body", "html_url", "section_id", "locale", "draft", "updated_at")
    if any(field not in data for field in fields):
        raise FetchError("Zendesk page contains an article with missing fields")
    if (
        any(type(data[key]) is not int or data[key] <= 0 for key in ("id", "section_id"))
        or any(
            not isinstance(data[key], str)
            for key in ("title", "body", "html_url", "locale", "updated_at")
        )
        or type(data["draft"]) is not bool
    ):
        raise FetchError("Zendesk page contains invalid article fields")
    return Article(
        id=data["id"],
        title=data["title"],
        body_html=data["body"],
        html_url=data["html_url"],
        section_id=data["section_id"],
        locale=data["locale"],
        draft=data["draft"],
        updated_at=data["updated_at"],
    )


def fetch_articles(get_json: Callable[[str], dict], base_url: str) -> list[Article]:
    """Return all pages of articles or fail closed if any page is incomplete."""
    url = f"{base_url.rstrip('/')}/api/v2/help_center/en-us/articles.json?per_page=100"
    origin = urlparse(url)
    seen: set[str] = set()
    articles: list[Article] = []
    while url:
        parsed = urlparse(url)
        if url in seen or (parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc):
            raise FetchError("Zendesk pagination repeated a page or left the configured origin")
        seen.add(url)
        try:
            page = get_json(url)
        except FetchError:
            raise
        except (requests.RequestException, ValueError, TypeError, KeyError, OSError) as exc:
            raise FetchError("Zendesk article pagination failed") from exc
        if (
            not isinstance(page, dict)
            or "next_page" not in page
            or not isinstance(page.get("articles"), list)
        ):
            raise FetchError("Zendesk returned an incomplete article page")
        articles.extend(_article(item) for item in page["articles"])
        next_page = page["next_page"]
        if next_page is not None and (not isinstance(next_page, str) or not next_page):
            raise FetchError("Zendesk returned an invalid next_page")
        url = next_page
    return articles


def select_articles(articles: Sequence[Article], selection: Selection) -> list[Article]:
    """Return eligible English articles ordered by selected section then article ID."""
    section_order = {section_id: index for index, section_id in enumerate(selection.section_ids)}
    selected = sorted(
        (
            article
            for article in articles
            if article.locale == LOCALE
            and not article.draft
            and article.section_id in section_order
        ),
        key=lambda article: (section_order[article.section_id], article.id),
    )
    if len(selected) < selection.min_articles:
        raise SelectionError(f"Selection below minimum of {selection.min_articles} articles")
    if not any(article.id == selection.youtube_article_id for article in selected):
        raise SelectionError("Required YouTube article is missing from selection")
    return selected
