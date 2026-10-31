"""Build safe run metadata and write or publish it through thin injectable edges."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

from rillmark.errors import PublishError
from rillmark.models import (
    ArticleDoc,
    ChunkBasis,
    ChunkConfig,
    Publisher,
    PublishStatus,
    RunMode,
    RunResult,
    RunStatus,
    Stage,
    StoreCounts,
)

# Generic categories guarantee that arbitrary diagnostics and user text cannot enter the gist.
_PUBLIC_ERROR_MESSAGES: dict[Stage, str] = {
    Stage.CONFIG: "Configuration failed.",
    Stage.FETCH: "Source fetch failed.",
    Stage.SELECT: "Article selection failed.",
    Stage.CONVERT: "Article conversion failed.",
    Stage.RESOLVE_STORE: "Store resolution failed.",
    Stage.LIST_REMOTE: "Remote file listing failed.",
    Stage.UPLOAD: "Upload failed.",
    Stage.ATTACH: "File attachment failed.",
    Stage.POLL: "File completion check failed.",
    Stage.DETACH: "Replacement cleanup failed.",
    Stage.PUBLISH: "Artifact publication failed.",
}


def estimate_chunks(docs: Sequence[ArticleDoc], chunk: ChunkConfig) -> tuple[int, ChunkBasis, int]:
    """Return the per-file overlap estimate, its hypothesis basis, and largest token size."""
    stride = chunk.max_tokens - chunk.overlap_tokens
    estimated = sum(
        max(1, (max(0, doc.tokens - chunk.overlap_tokens) + stride - 1) // stride) for doc in docs
    )
    largest = max((doc.tokens for doc in docs), default=0)
    basis = (
        ChunkBasis.SINGLE_CHUNK_INVARIANT
        if largest <= chunk.max_tokens
        else ChunkBasis.TIKTOKEN_ESTIMATE
    )
    return estimated, basis, largest


def build_last_run(result: RunResult, publish: PublishStatus) -> dict:
    """Return only the public schema fields, with unknown observations and chunks left null."""
    estimated, basis, largest = estimate_chunks(result.docs, result.chunk_config)
    return {
        "run_id": result.run_id,
        "status": result.status.value,
        "mode": result.mode.value,
        "publish": publish.value,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "git_sha": result.git_sha,
        "vector_store_id": result.vector_store_id,
        "counts": {
            "fetched": result.fetched,
            "selected": result.selected,
            "added": result.delta.added,
            "updated": result.delta.updated,
            "skipped": result.delta.skipped,
            "deleted": result.delta.deleted,
            "failed": result.delta.failed,
        },
        "store": _store_counts(result.store),
        "files": {
            "actual": result.store.files_completed if result.store is not None else None,
            "basis": "file_counts.completed",
        },
        "deletion_candidates": {
            "count": len(result.deletion_candidates),
            "article_ids": list(result.deletion_candidates),
        },
        "chunks": {
            "estimated": estimated,
            "basis": basis.value,
            "max_chunk_size_tokens": result.chunk_config.max_tokens,
            "largest_file_tokens": largest,
            "actual": None,
        },
        "errors": [
            {
                "article_id": error.article_id,
                "stage": error.stage.value,
                "message": _PUBLIC_ERROR_MESSAGES[error.stage],
            }
            for error in result.errors
        ],
    }


def _store_counts(store: StoreCounts | None) -> dict[str, int | None]:
    return {
        "files_in_store": store.files_in_store if store is not None else None,
        "files_completed": store.files_completed if store is not None else None,
        "managed_files_completed": store.managed_files_completed if store is not None else None,
    }


def summary_line(doc: dict) -> str:
    """Return a single log line distinguishing article, part-file, and estimated chunk counts."""
    fields = {
        "run_id": doc["run_id"],
        "mode": doc["mode"],
        "status": doc["status"],
        "selected_articles": doc["counts"]["selected"],
        "added_part_files": doc["counts"]["added"],
        "updated_part_files": doc["counts"]["updated"],
        "skipped_part_files": doc["counts"]["skipped"],
        "deleted_part_files": doc["counts"]["deleted"],
        "failed": doc["counts"]["failed"],
        "files": doc["files"]["actual"],
        "managed_files_completed": doc["store"]["managed_files_completed"],
        "all_store_files_completed": doc["store"]["files_completed"],
        "chunks_estimated": doc["chunks"]["estimated"],
        "chunks_actual": doc["chunks"]["actual"],
        "chunks_basis": doc["chunks"]["basis"],
        "deletion_candidates": doc["deletion_candidates"]["count"],
        "publish": doc["publish"],
    }
    return "summary " + " ".join(
        f"{key}={'null' if value is None else value}" for key, value in fields.items()
    )


def write_local(path: Path, doc: dict) -> None:
    """Write deterministic UTF-8 JSON with sorted keys and one trailing newline."""
    payload = json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8", newline="\n")


_RUN_FIELDS = frozenset(
    {"run_id", "started_at", "finished_at", "mode", "status", "publish", "git_sha", "counts"}
)
_COUNT_FIELDS = frozenset(
    {"fetched", "selected", "added", "updated", "skipped", "deleted", "failed"}
)
_LAST_RUN_FIELDS = _RUN_FIELDS | {
    "vector_store_id",
    "store",
    "files",
    "deletion_candidates",
    "chunks",
    "errors",
}
_HISTORY_LIMIT = 30


def _timestamp(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _count(value: object) -> bool:
    return type(value) is int and value >= 0


def _run_record(value: object) -> dict:
    if not isinstance(value, dict) or value.keys() != _RUN_FIELDS:
        raise PublishError("Invalid public run metadata.")
    if not all(_timestamp(value[key]) for key in ("run_id", "started_at", "finished_at")):
        raise PublishError("Invalid public run timestamp.")
    if value["run_id"] != value["started_at"] or value["finished_at"] < value["started_at"]:
        raise PublishError("Invalid public run order.")
    if (
        not isinstance(value["mode"], str)
        or value["mode"] not in RunMode
        or not isinstance(value["status"], str)
        or value["status"] not in RunStatus
        or not isinstance(value["publish"], str)
        or value["publish"] != PublishStatus.OK
    ):
        raise PublishError("Invalid public run status.")
    sha = value["git_sha"]
    if sha is not None and (
        not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{6,40}", sha)
    ):
        raise PublishError("Invalid public commit identifier.")
    counts = value["counts"]
    if not isinstance(counts, dict) or counts.keys() != _COUNT_FIELDS:
        raise PublishError("Invalid public run counts.")
    if not all(_count(n) for n in counts.values()):
        raise PublishError("Invalid public run counts.")
    return value


def _last_run(value: object) -> dict:
    if not isinstance(value, dict) or value.keys() != _LAST_RUN_FIELDS:
        raise PublishError("Invalid existing last-run artifact.")
    record = _run_record({key: value[key] for key in _RUN_FIELDS})
    store_id = value["vector_store_id"]
    if store_id is not None and (
        not isinstance(store_id, str) or not re.fullmatch(r"vs[-_][a-zA-Z0-9_-]+", store_id)
    ):
        raise PublishError("Invalid public store identifier.")
    store = value["store"]
    if (
        not isinstance(store, dict)
        or store.keys() != {"files_in_store", "files_completed", "managed_files_completed"}
        or not all(n is None or _count(n) for n in store.values())
    ):
        raise PublishError("Invalid public store counts.")
    files = value["files"]
    if not isinstance(files, dict) or files.keys() != {"actual", "basis"}:
        raise PublishError("Invalid public file counts.")
    if (files["actual"] is not None and not _count(files["actual"])) or files[
        "basis"
    ] != "file_counts.completed":
        raise PublishError("Invalid public file counts.")
    deletion = value["deletion_candidates"]
    if not isinstance(deletion, dict) or deletion.keys() != {"count", "article_ids"}:
        raise PublishError("Invalid public deletion candidates.")
    ids = deletion["article_ids"]
    if (
        not isinstance(ids, list)
        or not all(_count(n) for n in ids)
        or deletion["count"] != len(ids)
    ):
        raise PublishError("Invalid public deletion candidates.")
    chunks = value["chunks"]
    if not isinstance(chunks, dict) or chunks.keys() != {
        "estimated",
        "basis",
        "max_chunk_size_tokens",
        "largest_file_tokens",
        "actual",
    }:
        raise PublishError("Invalid public chunk estimate.")
    if (
        not isinstance(chunks["basis"], str)
        or chunks["basis"] not in ChunkBasis
        or chunks["actual"] is not None
        or not all(
            _count(chunks[key])
            for key in ("estimated", "max_chunk_size_tokens", "largest_file_tokens")
        )
    ):
        raise PublishError("Invalid public chunk estimate.")
    errors = value["errors"]
    if not isinstance(errors, list):
        raise PublishError("Invalid public errors.")
    for error in errors:
        if not isinstance(error, dict) or error.keys() != {"article_id", "stage", "message"}:
            raise PublishError("Invalid public errors.")
        stage = error["stage"]
        if (
            not isinstance(stage, str)
            or stage not in Stage
            or error["message"] != _PUBLIC_ERROR_MESSAGES[Stage(stage)]
            or (error["article_id"] is not None and not _count(error["article_id"]))
        ):
            raise PublishError("Invalid public errors.")
    return record


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise PublishError("Duplicate public JSON field.")
        value[key] = item
    return value


def _parse_public(content: str) -> object:
    try:
        return json.loads(content, object_pairs_hook=_unique_pairs)
    except (ValueError, TypeError):
        raise PublishError("Invalid public JSON artifact.") from None


def _gist_content(files: dict, name: str) -> str | None:
    if name not in files:
        return None
    file = files[name]
    if (
        not isinstance(file, dict)
        or file.get("truncated", False) is not False
        or not isinstance(file.get("content"), str)
    ):
        raise PublishError("Incomplete Gist artifact.")
    return file["content"]


class GistPublisher:
    """Read and atomically update a fixed Gist through injected GET and PATCH edges."""

    def __init__(
        self,
        gist_id: str,
        token: str,
        post: Callable[[str, dict, dict], tuple[int, dict]],
        get: Callable[[str, dict], tuple[int, dict]],
    ) -> None:
        self._url = f"https://api.github.com/gists/{gist_id}"
        self._token = token
        self._post = post
        self._get = get

    def publish(self, payload: str) -> str:
        """Publish two safe artifacts or fail closed without private diagnostics."""
        current = _parse_public(payload)
        current_record = _last_run(current)
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
        }
        try:
            status, response = self._get(self._url, headers)
        except Exception:
            raise PublishError("Gist read request failed.") from None
        if (
            status != 200
            or not isinstance(response, dict)
            or not isinstance(response.get("files"), dict)
        ):
            raise PublishError("Gist read returned an invalid response.")
        files = response["files"]
        history_content = _gist_content(files, "history.json")
        last_content = _gist_content(files, "last_run.json")
        if last_content is not None:
            previous = _parse_public(last_content)
            previous_record = _last_run(previous)
        else:
            previous_record = None
        if history_content is None:
            runs = []
        else:
            history = _parse_public(history_content)
            if (
                not isinstance(history, dict)
                or history.keys() != {"schema_version", "retention", "runs"}
                or type(history["schema_version"]) is not int
                or history["schema_version"] != 1
                or type(history["retention"]) is not int
                or history["retention"] != _HISTORY_LIMIT
                or not isinstance(history["runs"], list)
            ):
                raise PublishError("Invalid existing history artifact.")
            runs = history["runs"]
            for record in runs:
                _run_record(record)
            if len({record["run_id"] for record in runs}) != len(runs):
                raise PublishError("Duplicate run identifiers in history.")
        by_id = {record["run_id"]: record for record in runs}
        if previous_record is not None:
            if (
                previous_record["run_id"] in by_id
                and by_id[previous_record["run_id"]] != previous_record
            ):
                raise PublishError("Conflicting latest run metadata.")
            if any(record["run_id"] > previous_record["run_id"] for record in runs):
                raise PublishError("History is newer than the latest artifact.")
            by_id.setdefault(previous_record["run_id"], previous_record)
        elif any(record["run_id"] > current_record["run_id"] for record in runs):
            raise PublishError("Missing latest artifact for older run.")
        by_id[current_record["run_id"]] = current_record
        ordered = sorted(by_id.values(), key=lambda record: record["run_id"], reverse=True)[
            :_HISTORY_LIMIT
        ]
        history_payload = (
            json.dumps(
                {"schema_version": 1, "retention": _HISTORY_LIMIT, "runs": ordered},
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        latest_payload = (
            last_content
            if previous_record is not None and previous_record["run_id"] > current_record["run_id"]
            else payload
        )
        body = {
            "files": {
                "last_run.json": {"content": latest_payload},
                "history.json": {"content": history_payload},
            }
        }
        try:
            status, response = self._post(self._url, headers, body)
        except Exception:
            raise PublishError("Gist publication request failed.") from None
        if not 200 <= status < 300:
            raise PublishError("Gist publication returned a non-success status.")
        if (
            not isinstance(response, dict)
            or not isinstance(response.get("html_url"), str)
            or not response["html_url"]
        ):
            raise PublishError("Gist publication returned no public URL.")
        return response["html_url"]


def publish_artifact(publisher: Publisher | None, payload: str) -> PublishStatus:
    """Return skipped, ok, or failed for an optional publisher without changing the sync result."""
    if publisher is None:
        return PublishStatus.SKIPPED
    try:
        publisher.publish(payload)
    except PublishError:
        return PublishStatus.FAILED
    return PublishStatus.OK
