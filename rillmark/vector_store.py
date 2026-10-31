"""Thin, injectable OpenAI vector-store edge; no provider calls at import time."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from openai import OpenAI, OpenAIError

from rillmark.errors import RemoteStateError, StoreResolutionError, UploadError
from rillmark.models import (
    MANAGED_BY,
    STORE_NAME,
    ArticleDoc,
    ChunkConfig,
    FileStatus,
    RemoteFile,
    StoreCounts,
)

REQUEST_TIMEOUT_S: float = 30.0
POLL_INITIAL_S: float = 0.5
POLL_MAX_S: float = 5.0
SDK_ERRORS: tuple[type[Exception], ...] = (
    OpenAIError,
    RuntimeError,
    ValueError,
    KeyError,
    AttributeError,
    TypeError,
)


def make_client(api_key: str) -> OpenAI:
    """Construct a provider client with a bounded request timeout."""
    # The SDK otherwise retries POST uploads/attachments as well as idempotent reads.
    return OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_S, max_retries=0)


def _remote_file(item: Any) -> RemoteFile:
    """Translate one SDK vector-store attachment to the shared contract."""
    return RemoteFile(
        file_id=item.id,
        status=FileStatus(item.status),
        attributes=item.attributes or {},
        created_at=item.created_at or 0,
    )


class OpenAIStoreGateway:
    """Implement StoreGateway using only store-scoped attachment operations."""

    def __init__(
        self,
        client: Any,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._sleep = sleep
        self._clock = clock

    def resolve_store(self, explicit_id: str | None) -> str:
        """Return the unique marked store ID or fail closed on ambiguity/errors."""
        stores = self._client.vector_stores
        if explicit_id is not None:
            try:
                item = stores.retrieve(explicit_id, timeout=REQUEST_TIMEOUT_S)
                if item.metadata is None or item.metadata.get("managed_by") != MANAGED_BY:
                    raise StoreResolutionError("Explicit vector store lacks the ownership marker")
                return item.id
            except SDK_ERRORS as exc:
                raise StoreResolutionError("Cannot retrieve explicit vector store") from exc

        try:
            matches = [
                item.id
                for item in stores.list(timeout=REQUEST_TIMEOUT_S)
                if item.metadata is not None and item.metadata.get("managed_by") == MANAGED_BY
            ]
        except SDK_ERRORS as exc:
            raise StoreResolutionError("Cannot completely list vector stores") from exc
        if len(matches) > 1:
            raise StoreResolutionError("Multiple vector stores have the ownership marker")
        if matches:
            return matches[0]
        try:
            item = stores.create(
                name=STORE_NAME, metadata={"managed_by": MANAGED_BY}, timeout=REQUEST_TIMEOUT_S
            )
            if item.metadata is None or item.metadata.get("managed_by") != MANAGED_BY:
                raise StoreResolutionError("Created vector store lacks the ownership marker")
            return item.id
        except SDK_ERRORS as exc:
            raise StoreResolutionError("Cannot create marked vector store") from exc

    def list_files(self, store_id: str) -> list[RemoteFile]:
        """Return every attachment, retrieving missing attributes; never return partial state."""
        files = self._client.vector_stores.files
        try:
            result: list[RemoteFile] = []
            for item in files.list(store_id, timeout=REQUEST_TIMEOUT_S):
                if item.attributes is None:
                    item = files.retrieve(
                        item.id, vector_store_id=store_id, timeout=REQUEST_TIMEOUT_S
                    )
                    # A confirmed explicit null is unowned; an omitted field is incomplete state.
                    fields = getattr(item, "model_fields_set", vars(item).keys())
                    if "attributes" not in fields:
                        raise RemoteStateError("Attachment attributes unavailable after retrieval")
                result.append(_remote_file(item))
            return result
        except SDK_ERRORS as exc:
            raise RemoteStateError("Cannot completely list vector-store files") from exc

    def upload(
        self,
        store_id: str,
        doc: ArticleDoc,
        attributes: Mapping[str, str | int],
        chunk: ChunkConfig,
    ) -> RemoteFile:
        """Upload Markdown and attach it with source attributes and static chunking."""
        try:
            uploaded = self._client.files.create(
                purpose="assistants",
                file=(doc.filename, doc.markdown.encode("utf-8")),
                timeout=REQUEST_TIMEOUT_S,
            )
            attached = self._client.vector_stores.files.create(
                store_id,
                file_id=uploaded.id,
                attributes=dict(attributes),
                chunking_strategy={
                    "type": "static",
                    "static": {
                        "max_chunk_size_tokens": chunk.max_tokens,
                        "chunk_overlap_tokens": chunk.overlap_tokens,
                    },
                },
                timeout=REQUEST_TIMEOUT_S,
            )
            return _remote_file(attached)
        except SDK_ERRORS as exc:
            # A successfully uploaded File may remain orphaned; never globally delete it.
            raise UploadError("File upload or vector-store attachment failed") from exc

    def wait_completed(self, store_id: str, file_id: str, timeout_s: float) -> RemoteFile:
        """Poll with bounded exponential backoff; fail on terminal errors or deadline."""
        deadline = self._clock() + max(0.0, timeout_s)
        delay = POLL_INITIAL_S
        while True:
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise UploadError("Vector-store attachment timed out")
            try:
                item = self._client.vector_stores.files.retrieve(
                    file_id, vector_store_id=store_id, timeout=min(REQUEST_TIMEOUT_S, remaining)
                )
                remote = _remote_file(item)
            except SDK_ERRORS as exc:
                raise UploadError("Cannot poll vector-store attachment") from exc
            if self._clock() >= deadline:
                raise UploadError("Vector-store attachment timed out")
            if remote.status is FileStatus.COMPLETED:
                return remote
            if remote.status in (FileStatus.FAILED, FileStatus.CANCELLED):
                raise UploadError("Vector-store attachment failed or was cancelled")
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise UploadError("Vector-store attachment timed out")
            self._sleep(min(delay, remaining))
            delay = min(delay * 2, POLL_MAX_S)

    def detach(self, store_id: str, file_id: str) -> None:
        """Detach only from the resolved store, never delete a global File."""
        try:
            result = self._client.vector_stores.files.delete(
                file_id, vector_store_id=store_id, timeout=REQUEST_TIMEOUT_S
            )
            if not result.deleted:
                raise UploadError("Vector-store attachment was not detached")
        except SDK_ERRORS as exc:
            raise UploadError("Cannot detach vector-store attachment") from exc

    def counts(self, store_id: str) -> StoreCounts:
        """Return observed store counts and completed owned attachments."""
        try:
            item = self._client.vector_stores.retrieve(store_id, timeout=REQUEST_TIMEOUT_S)
            total = item.file_counts.total
            completed = item.file_counts.completed
        except SDK_ERRORS as exc:
            raise RemoteStateError("Cannot retrieve vector-store file counts") from exc
        managed = sum(
            entry.managed and entry.status is FileStatus.COMPLETED
            for entry in self.list_files(store_id)
        )
        return StoreCounts(total, completed, managed)
