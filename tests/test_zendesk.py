"""Offline Zendesk pagination, selection and HTTP behavior checks."""

import pytest
import requests

from rillmark.errors import FetchError, SelectionError
from rillmark.models import Selection
from rillmark.zendesk import fetch_articles, http_get_json, select_articles

BASE = "https://support.optisigns.com"
FIRST = f"{BASE}/api/v2/help_center/en-us/articles.json?per_page=100"


def article_data(article_id: int, **changes: object) -> dict[str, object]:
    """Return only fields consumed from the provider's article JSON."""
    data: dict[str, object] = {
        "id": article_id,
        "title": "A title",
        "body": "<p>Body</p>",
        "html_url": f"{BASE}/hc/en-us/articles/{article_id}",
        "section_id": 10,
        "locale": "en-us",
        "draft": False,
        "updated_at": "2026-01-01T00:00:00Z",
    }
    data.update(changes)
    return data


def test_fetch_articles_follows_three_pages() -> None:
    pages = {
        FIRST: {"articles": [article_data(1)], "next_page": f"{BASE}/page/2"},
        f"{BASE}/page/2": {"articles": [article_data(2)], "next_page": f"{BASE}/page/3"},
        f"{BASE}/page/3": {"articles": [article_data(3)], "next_page": None},
    }
    visited: list[str] = []

    def get_json(url: str) -> dict:
        visited.append(url)
        return pages[url]

    result = fetch_articles(get_json, BASE + "/")
    assert [a.id for a in result] == [1, 2, 3]
    assert visited == list(pages)
    assert result[0].body_html == "<p>Body</p>"


def test_fetch_articles_failure_mid_pagination_never_returns_partial() -> None:
    def get_json(url: str) -> dict:
        if url == FIRST:
            return {"articles": [article_data(1)], "next_page": f"{BASE}/page/2"}
        raise requests.Timeout("fetch timed out")

    with pytest.raises(FetchError):
        fetch_articles(get_json, BASE)


@pytest.mark.parametrize(
    "page",
    [
        {"articles": [article_data(1)]},
        {"articles": [article_data(1)], "next_page": "/repeat"},
        {"articles": [article_data(1), {"id": 2}], "next_page": None},
        {"articles": "not a list", "next_page": None},
    ],
)
def test_fetch_articles_rejects_incomplete_or_malformed_pages(page: dict) -> None:
    def get_json(url: str) -> dict:
        if url == FIRST:
            return page
        return {"articles": [article_data(2)], "next_page": "/repeat"}

    with pytest.raises(FetchError):
        fetch_articles(get_json, BASE)


def test_select_articles_filters_and_orders_by_section_then_id() -> None:
    source = [
        article_data(7, section_id=20),
        article_data(8, section_id=10, draft=True),
        article_data(2, section_id=10),
        article_data(4, section_id=20, locale="fr"),
        article_data(5, section_id=30),
        article_data(1, section_id=20),
    ]
    articles = fetch_articles(lambda _: {"articles": source, "next_page": None}, BASE)
    selected = select_articles(articles, Selection((20, 10), youtube_article_id=2, min_articles=3))
    assert [a.id for a in selected] == [1, 7, 2]


def test_select_articles_rejects_below_minimum() -> None:
    articles = fetch_articles(lambda _: {"articles": [article_data(1)], "next_page": None}, BASE)
    with pytest.raises(SelectionError, match="minimum"):
        select_articles(articles, Selection((10,), youtube_article_id=1, min_articles=30))


def test_select_articles_rejects_missing_youtube() -> None:
    articles = fetch_articles(
        lambda _: {"articles": [article_data(1), article_data(2)], "next_page": None}, BASE
    )
    with pytest.raises(SelectionError, match="YouTube"):
        select_articles(articles, Selection((10,), youtube_article_id=99, min_articles=2))


class FakeResponse:
    """Small HTTP response fake with a configurable status and JSON payload."""

    def __init__(self, status: int, payload: object = None, retry_after: str | None = None) -> None:
        self.status_code = status
        self.headers = {"Retry-After": retry_after} if retry_after else {}
        self.payload = payload

    def raise_for_status(self) -> None:
        """Emulate requests status raising."""
        if self.status_code >= 400:
            raise requests.HTTPError("HTTP failure")

    def json(self) -> object:
        """Return the fake decoded JSON."""
        return self.payload


def test_http_get_json_retries_429_honoring_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[tuple[str, tuple[int, int]]] = []
    pauses: list[float] = []
    responses = iter([FakeResponse(429, retry_after="2"), FakeResponse(200, {"ok": True})])

    def fake_get(url: str, *, timeout: tuple[int, int]) -> FakeResponse:
        attempts.append((url, timeout))
        return next(responses)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("rillmark.zendesk.time.sleep", pauses.append)
    assert http_get_json(FIRST) == {"ok": True}
    assert attempts == [(FIRST, (5, 30)), (FIRST, (5, 30))]
    assert pauses == [2]


def test_http_get_json_fails_after_three_5xx_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[str] = []
    pauses: list[float] = []

    def fake_get(url: str, *, timeout: tuple[int, int]) -> FakeResponse:
        attempts.append(url)
        return FakeResponse(503)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("rillmark.zendesk.time.sleep", pauses.append)
    with pytest.raises(FetchError):
        http_get_json(FIRST)
    assert len(attempts) == 3
    assert pauses == [1, 2]


def test_http_get_json_does_not_retry_4xx_or_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    def fake_get(url: str, *, timeout: tuple[int, int]) -> FakeResponse:
        attempts.append(1)
        return FakeResponse(404)

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(FetchError):
        http_get_json(FIRST)
    assert len(attempts) == 1
    monkeypatch.setattr(requests, "get", lambda url, timeout: FakeResponse(200, [1]))
    with pytest.raises(FetchError):
        http_get_json(FIRST)
