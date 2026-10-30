"""Build safe run metadata and write or publish it through thin injectable edges."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path

from rillmark.errors import PublishError
from rillmark.models import (
    ArticleDoc,
    ChunkBasis,
    ChunkConfig,
    Publisher,
    PublishStatus,
    RunResult,
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


class GistPublisher:
    """Update a fixed gist using an injected PATCH adapter with its own HTTP timeouts."""

    def __init__(
        self,
        gist_id: str,
        token: str,
        post: Callable[[str, dict, dict], tuple[int, dict]],
    ) -> None:
        self._url = f"https://api.github.com/gists/{gist_id}"
        self._token = token
        self._post = post

    def publish(self, payload: str) -> str:
        """Return the gist public URL or raise PublishError without private diagnostics."""
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
        }
        body = {"files": {"last_run.json": {"content": payload}}}
        try:
            status, response = self._post(self._url, headers, body)
        except Exception:
            # The injected edge may raise any transport error; do not expose its text or chain.
            raise PublishError("Gist publication request failed.") from None
        if not 200 <= status < 300:
            raise PublishError("Gist publication returned a non-success status.")
        url = response.get("html_url")
        if not isinstance(url, str) or not url:
            raise PublishError("Gist publication returned no public URL.")
        return url


def publish_artifact(publisher: Publisher | None, payload: str) -> PublishStatus:
    """Return skipped, ok, or failed for an optional publisher without changing the sync result."""
    if publisher is None:
        return PublishStatus.SKIPPED
    try:
        publisher.publish(payload)
    except PublishError:
        return PublishStatus.FAILED
    return PublishStatus.OK
