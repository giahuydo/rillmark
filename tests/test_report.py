"""Offline checks for the public run artifact and its injected publishing edge."""

from __future__ import annotations

import json
import traceback
from dataclasses import replace
from pathlib import Path

import pytest

from rillmark.errors import PublishError
from rillmark.models import (
    ArticleDoc,
    ChunkBasis,
    ChunkConfig,
    DeltaCounts,
    ErrorRecord,
    PublishStatus,
    RunMode,
    RunResult,
    RunStatus,
    Stage,
    StoreCounts,
)
from rillmark.report import (
    GistPublisher,
    build_last_run,
    estimate_chunks,
    publish_artifact,
    summary_line,
    write_local,
)


@pytest.fixture
def result() -> RunResult:
    """Return synthetic metadata containing no source article content."""
    return RunResult(
        run_id="2026-11-02T03:00:04Z",
        mode=RunMode.SYNC,
        status=RunStatus.SUCCESS,
        started_at="2026-11-02T03:00:04Z",
        finished_at="2026-11-02T03:01:04Z",
        git_sha="abc123",
        vector_store_id="vs-example",
        fetched=37,
        selected=30,
        delta=DeltaCounts(added=2, updated=1, skipped=27, deleted=1, failed=0),
        store=StoreCounts(files_in_store=33, files_completed=32, managed_files_completed=30),
        deletion_candidates=(101, 102),
        docs=(make_doc(80), make_doc(100, part=2)),
        chunk_config=ChunkConfig(max_tokens=100, overlap_tokens=20),
    )


def make_doc(tokens: int, part: int = 1) -> ArticleDoc:
    return ArticleDoc(
        article_id=100,
        part=part,
        slug="example",
        title="Private title must not enter the artifact",
        url="https://example.test/article/100",
        section_id=200,
        source_updated_at="2026-10-30T00:00:00Z",
        markdown="# Private source body must not enter the artifact\n",
        tokens=tokens,
    )


def test_build_last_run_matches_exact_schema(result: RunResult) -> None:
    doc = build_last_run(result, PublishStatus.OK)

    assert doc == {
        "run_id": result.run_id,
        "status": "success",
        "mode": "sync",
        "publish": "ok",
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "git_sha": "abc123",
        "vector_store_id": "vs-example",
        "counts": {
            "fetched": 37,
            "selected": 30,
            "added": 2,
            "updated": 1,
            "skipped": 27,
            "deleted": 1,
            "failed": 0,
        },
        "store": {
            "files_in_store": 33,
            "files_completed": 32,
            "managed_files_completed": 30,
        },
        "files": {"actual": 32, "basis": "file_counts.completed"},
        "deletion_candidates": {"count": 2, "article_ids": [101, 102]},
        "chunks": {
            "estimated": 2,
            "basis": "single-chunk-invariant",
            "max_chunk_size_tokens": 100,
            "largest_file_tokens": 100,
            "actual": None,
        },
        "errors": [],
    }
    assert "Private" not in json.dumps(doc)


@pytest.mark.parametrize("mode", [RunMode.SYNC, RunMode.PILOT, RunMode.DRY_RUN])
def test_build_last_run_keeps_unobserved_counts_null(result: RunResult, mode: RunMode) -> None:
    result = replace(result, mode=mode, store=None, vector_store_id=None, git_sha=None)

    doc = build_last_run(result, PublishStatus.SKIPPED)

    assert doc["store"] == {
        "files_in_store": None,
        "files_completed": None,
        "managed_files_completed": None,
    }
    assert doc["files"] == {"actual": None, "basis": "file_counts.completed"}
    assert doc["chunks"]["actual"] is None
    assert doc["mode"] == mode.value
    assert doc["git_sha"] is None
    assert doc["vector_store_id"] is None


def test_build_last_run_preserves_observed_zero_files(result: RunResult) -> None:
    result = replace(result, store=StoreCounts(0, 0, 0), deletion_candidates=())

    doc = build_last_run(result, PublishStatus.OK)

    assert doc["files"]["actual"] == 0
    assert doc["store"] == {
        "files_in_store": 0,
        "files_completed": 0,
        "managed_files_completed": 0,
    }
    assert doc["deletion_candidates"] == {"count": 0, "article_ids": []}


@pytest.mark.parametrize("status", [RunStatus.PARTIAL_FAILURE, RunStatus.FAILED])
@pytest.mark.parametrize("publish", list(PublishStatus))
def test_build_last_run_preserves_sync_failure(
    result: RunResult, status: RunStatus, publish: PublishStatus
) -> None:
    error = ErrorRecord(Stage.UPLOAD, "Upload failed.", article_id=100)
    result = replace(result, status=status, delta=DeltaCounts(failed=1), errors=(error,))

    doc = build_last_run(result, publish)

    assert doc["status"] == status.value
    assert doc["publish"] == publish.value
    assert doc["counts"]["failed"] == 1
    assert doc["errors"] == [{"article_id": 100, "stage": "upload", "message": "Upload failed."}]


@pytest.mark.parametrize(
    ("tokens", "overlap", "estimated", "basis", "largest"),
    [
        ([], 20, 0, ChunkBasis.SINGLE_CHUNK_INVARIANT, 0),
        ([0], 20, 1, ChunkBasis.SINGLE_CHUNK_INVARIANT, 0),
        ([1, 20, 99, 100], 20, 4, ChunkBasis.SINGLE_CHUNK_INVARIANT, 100),
        ([101], 20, 2, ChunkBasis.TIKTOKEN_ESTIMATE, 101),
        ([180], 20, 2, ChunkBasis.TIKTOKEN_ESTIMATE, 180),
        ([181], 20, 3, ChunkBasis.TIKTOKEN_ESTIMATE, 181),
        ([200], 20, 3, ChunkBasis.TIKTOKEN_ESTIMATE, 200),
        ([200], 0, 2, ChunkBasis.TIKTOKEN_ESTIMATE, 200),
        ([0, 100, 181], 20, 5, ChunkBasis.TIKTOKEN_ESTIMATE, 181),
    ],
)
def test_estimate_chunks_counts_each_part_with_overlap(
    tokens: list[int], overlap: int, estimated: int, basis: ChunkBasis, largest: int
) -> None:
    docs = [make_doc(count, part=index + 1) for index, count in enumerate(tokens)]

    actual = estimate_chunks(docs, ChunkConfig(max_tokens=100, overlap_tokens=overlap))

    assert actual == (estimated, basis, largest)


def test_build_last_run_reports_estimate_basis_without_actual_chunks(result: RunResult) -> None:
    result = replace(result, docs=(make_doc(181),))

    doc = build_last_run(result, PublishStatus.OK)

    assert doc["chunks"] == {
        "estimated": 3,
        "basis": "tiktoken-estimate",
        "max_chunk_size_tokens": 100,
        "largest_file_tokens": 181,
        "actual": None,
    }


@pytest.mark.parametrize(
    "sensitive",
    [
        "sk-example-secret",
        "sk-proj-example_secret",
        "ghp_exampleSecret",
        "gho_exampleSecret",
        "ghs_exampleSecret",
        "github_pat_exampleSecret",
        "Bearer opaque-private-value",
        "https://example.test/upload?token=private&name=someone",
        "person@example.test",
    ],
)
def test_build_last_run_redacts_sensitive_error_details(result: RunResult, sensitive: str) -> None:
    result = replace(result, errors=(ErrorRecord(Stage.PUBLISH, f"Request failed: {sensitive}"),))

    doc = build_last_run(result, PublishStatus.FAILED)
    message = doc["errors"][0]["message"]

    assert sensitive not in json.dumps(doc)
    assert len(message) <= 200
    assert doc["errors"][0]["article_id"] is None
    assert doc["errors"][0]["stage"] == "publish"


@pytest.mark.parametrize(
    "message",
    [
        "Traceback (most recent call last):\nprivate source text",
        "<html><body>Private article content</body></html>",
        "Request headers: X-Private-Key: private-value",
        "User says: private details for Alice Smith",
        "RuntimeError: private diagnostic text",
        "Request failed for https://example.test/private/article",
    ],
)
def test_build_last_run_omits_raw_error_content(result: RunResult, message: str) -> None:
    result = replace(result, errors=(ErrorRecord(Stage.FETCH, message),))

    doc = build_last_run(result, PublishStatus.FAILED)

    assert "private" not in json.dumps(doc).lower()
    assert "traceback" not in json.dumps(doc).lower()
    assert "<html>" not in json.dumps(doc)


def test_build_last_run_sanitizes_before_truncating_error(result: RunResult) -> None:
    message = "x" * 195 + " sk-private-value"
    result = replace(result, errors=(ErrorRecord(Stage.UPLOAD, message),))

    safe = build_last_run(result, PublishStatus.OK)["errors"][0]["message"]

    assert len(safe) <= 200
    assert "sk-" not in safe


@pytest.mark.parametrize("stage", list(Stage))
def test_build_last_run_uses_generic_message_for_each_stage(
    result: RunResult, stage: Stage
) -> None:
    result = replace(result, errors=(ErrorRecord(stage, "Arbitrary diagnostic content"),))

    error = build_last_run(result, PublishStatus.FAILED)["errors"][0]

    assert error["stage"] == stage.value
    assert error["article_id"] is None
    assert 0 < len(error["message"]) <= 200
    assert "Arbitrary diagnostic content" not in error["message"]


def test_summary_line_reports_units_and_publication(result: RunResult) -> None:
    result = replace(result, mode=RunMode.PILOT)

    line = summary_line(build_last_run(result, PublishStatus.SKIPPED))

    assert line.startswith("summary ")
    assert "\n" not in line
    fields = dict(field.split("=", 1) for field in line.split()[1:])
    assert (
        fields.items()
        >= {
            "mode": "pilot",
            "status": "success",
            "selected_articles": "30",
            "added_part_files": "2",
            "updated_part_files": "1",
            "skipped_part_files": "27",
            "deleted_part_files": "1",
            "failed": "0",
            "files": "32",
            "chunks_estimated": "2",
            "chunks_actual": "null",
            "chunks_basis": "single-chunk-invariant",
            "publish": "skipped",
        }.items()
    )


def test_summary_line_reports_unknown_files_as_null(result: RunResult) -> None:
    doc = build_last_run(replace(result, store=None), PublishStatus.FAILED)

    fields = summary_line(doc).split()

    assert "files=null" in fields
    assert "publish=failed" in fields


def test_write_local_round_trips_utf8_sorted_json(tmp_path: Path) -> None:
    path = tmp_path / "last_run.json"
    doc = {"z": "café", "a": {"z": 2, "a": None}}

    write_local(path, doc)

    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert "café" in text
    assert text.index('"a"') < text.index('"z"')
    assert json.loads(text) == doc


class FakePoster:
    def __init__(
        self,
        status: int = 200,
        body: dict | None = None,
        error: Exception | None = None,
    ) -> None:
        self.status = status
        self.body = {"html_url": "https://gist.github.com/example/123"} if body is None else body
        self.error = error
        self.calls: list[tuple[str, dict, dict]] = []

    def __call__(self, url: str, headers: dict, body: dict) -> tuple[int, dict]:
        self.calls.append((url, headers, body))
        if self.error is not None:
            raise self.error
        return self.status, self.body


def test_gist_publisher_sends_fixed_file_to_injected_patch() -> None:
    poster = FakePoster()
    publisher = GistPublisher("123", "ghp_fakeTestToken", poster)
    payload = '{"run_id":"example"}\n'

    url = publisher.publish(payload)

    assert url == "https://gist.github.com/example/123"
    assert len(poster.calls) == 1
    request_url, headers, body = poster.calls[0]
    assert request_url == "https://api.github.com/gists/123"
    assert headers["Authorization"] == "Bearer ghp_fakeTestToken"
    assert headers["Accept"] == "application/vnd.github+json"
    assert body == {"files": {"last_run.json": {"content": payload}}}


@pytest.mark.parametrize("status", [200, 201, 299])
def test_gist_publisher_accepts_success_status(status: int) -> None:
    publisher = GistPublisher("123", "fake-token", FakePoster(status=status))

    assert publisher.publish("{}") == "https://gist.github.com/example/123"


@pytest.mark.parametrize("status", [199, 300, 401, 429, 500])
def test_gist_publisher_rejects_non_success_without_response_details(status: int) -> None:
    token = "ghp_fakeTestToken"
    poster = FakePoster(status=status, body={"message": token})
    publisher = GistPublisher("123", token, poster)

    with pytest.raises(PublishError) as caught:
        publisher.publish("{}")

    assert token not in str(caught.value)
    assert len(poster.calls) == 1


@pytest.mark.parametrize("error_type", [OSError, TimeoutError, ValueError, RuntimeError])
def test_gist_publisher_wraps_callback_exception_without_token(
    error_type: type[Exception],
) -> None:
    token = "ghp_fakeTestToken"
    publisher = GistPublisher("123", token, FakePoster(error=error_type(f"Bearer {token}")))

    with pytest.raises(PublishError) as caught:
        publisher.publish("{}")

    assert token not in str(caught.value)
    assert token not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("body", [{}, {"html_url": None}, {"html_url": 123}, {"html_url": ""}])
def test_gist_publisher_rejects_missing_public_url(body: dict) -> None:
    publisher = GistPublisher("123", "fake-token", FakePoster(body=body))

    with pytest.raises(PublishError):
        publisher.publish("{}")


@pytest.mark.parametrize(
    ("publisher", "expected"),
    [
        (None, PublishStatus.SKIPPED),
        (GistPublisher("123", "fake-token", FakePoster()), PublishStatus.OK),
        (GistPublisher("123", "fake-token", FakePoster(status=503)), PublishStatus.FAILED),
        (
            GistPublisher("123", "fake-token", FakePoster(error=OSError("Unavailable"))),
            PublishStatus.FAILED,
        ),
    ],
)
def test_publish_artifact_maps_optional_publisher_outcome(
    publisher: GistPublisher | None, expected: PublishStatus
) -> None:
    assert publish_artifact(publisher, "{}") is expected
