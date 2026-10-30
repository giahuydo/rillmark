"""Shared data contracts between modules. Frozen: change only through the integrator.

Design references: docs/02-data-contracts.md (§1 input, §2 file, §4 attributes, §5 artifact),
docs/03-sync-lifecycle.md (§2 state, §3 classification, §6 exits).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

MANAGED_BY = "rillmark-optibot-v1"
STORE_NAME = "rillmark-optibot"
SCHEMA_VERSION = 1
LOCALE = "en-us"


class RunMode(StrEnum):
    SYNC = "sync"
    PILOT = "pilot"
    DRY_RUN = "dry-run"


class RunStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


class PublishStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


class ChunkBasis(StrEnum):
    SINGLE_CHUNK_INVARIANT = "single-chunk-invariant"
    TIKTOKEN_ESTIMATE = "tiktoken-estimate"


class Stage(StrEnum):
    """Allowlisted error stages for the public artifact."""

    CONFIG = "config"
    FETCH = "fetch"
    SELECT = "select"
    CONVERT = "convert"
    RESOLVE_STORE = "resolve_store"
    LIST_REMOTE = "list_remote"
    UPLOAD = "upload"
    ATTACH = "attach"
    POLL = "poll"
    DETACH = "detach"
    PUBLISH = "publish"


class FileStatus(StrEnum):
    """Vector-store file attachment status as reported by the provider."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class Selection:
    """Versioned article selection (config/selection.json, env overrides applied)."""

    section_ids: tuple[int, ...]
    youtube_article_id: int
    min_articles: int


@dataclass(frozen=True, slots=True)
class ChunkConfig:
    """Static chunking settings; part of the content hash (docs/03 §2)."""

    max_tokens: int
    overlap_tokens: int


@dataclass(frozen=True, slots=True)
class Article:
    """One Zendesk article as fetched (docs/02 §1). Only consumed fields are kept."""

    id: int
    title: str
    body_html: str
    html_url: str
    section_id: int
    locale: str
    draft: bool
    updated_at: str


@dataclass(frozen=True, slots=True)
class ArticleDoc:
    """One generated Markdown file (docs/02 §2). Unsplit articles are part 1."""

    article_id: int
    part: int
    slug: str
    title: str
    url: str
    section_id: int
    source_updated_at: str
    markdown: str
    tokens: int

    @property
    def key(self) -> str:
        """Canonical sync key `article_id/part`."""
        return f"{self.article_id}/{self.part}"

    @property
    def filename(self) -> str:
        return f"{self.slug}.md" if self.part == 1 else f"{self.slug}--p{self.part}.md"


@dataclass(frozen=True, slots=True)
class RemoteFile:
    """One attachment in the resolved vector store (docs/03 §2)."""

    file_id: str
    status: FileStatus
    attributes: Mapping[str, str | int | float | bool] = field(default_factory=dict)
    created_at: int = 0

    @property
    def managed(self) -> bool:
        return self.attributes.get("managed_by") == MANAGED_BY

    @property
    def key(self) -> str | None:
        """`article_id/part` for managed files, else None."""
        if not self.managed or "article_id" not in self.attributes:
            return None
        return f"{self.attributes['article_id']}/{int(self.attributes.get('part', 1))}"


@dataclass(frozen=True, slots=True)
class Replacement:
    """An updated or retried file: upload `new`, then detach `old` once `new` completes."""

    new: ArticleDoc
    old: RemoteFile


@dataclass(frozen=True, slots=True)
class DeltaPlan:
    """Result of pure delta classification (docs/03 §3)."""

    added: tuple[ArticleDoc, ...]
    updated: tuple[Replacement, ...]
    skipped: tuple[ArticleDoc, ...]
    retried: tuple[Replacement, ...]  # owned entry only failed/cancelled; counts as added
    deletion_candidates: tuple[int, ...]  # article IDs; logged only, never deleted
    duplicates: tuple[RemoteFile, ...]  # surplus owned completed files for the same key


@dataclass(frozen=True, slots=True)
class ErrorRecord:
    """Public-safe error entry: numeric article ID, allowlisted stage, generic message."""

    stage: Stage
    message: str
    article_id: int | None = None


@dataclass(frozen=True, slots=True)
class StoreCounts:
    files_in_store: int
    files_completed: int
    managed_files_completed: int


@dataclass(frozen=True, slots=True)
class DeltaCounts:
    """File-attachment operations by `article_id/part`, not articles or chunks."""

    added: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0  # successful replacement detaches only
    failed: int = 0


@dataclass(frozen=True, slots=True)
class RunResult:
    """Everything report.py needs to build last_run.json (docs/02 §5)."""

    run_id: str
    mode: RunMode
    status: RunStatus
    started_at: str
    finished_at: str
    git_sha: str | None
    vector_store_id: str | None
    fetched: int
    selected: int
    delta: DeltaCounts
    store: StoreCounts | None  # None when not observed (dry-run or listing failed)
    deletion_candidates: tuple[int, ...]
    docs: tuple[ArticleDoc, ...]
    chunk_config: ChunkConfig
    errors: tuple[ErrorRecord, ...] = ()


class StoreGateway(Protocol):
    """Thin OpenAI vector-store edge (rillmark/vector_store.py). Tests use an in-memory fake."""

    def resolve_store(self, explicit_id: str | None) -> str:
        """Return the marked store ID: validate explicit ID, else 0→create, 1→reuse, >1→raise."""
        ...

    def list_files(self, store_id: str) -> list[RemoteFile]:
        """All attachments across all pages; raise RemoteStateError if incomplete."""
        ...

    def upload(
        self,
        store_id: str,
        doc: ArticleDoc,
        attributes: Mapping[str, str | int],
        chunk: ChunkConfig,
    ) -> RemoteFile:
        """Upload the file, attach it with attributes and static chunking; return the attachment."""
        ...

    def wait_completed(self, store_id: str, file_id: str, timeout_s: float) -> RemoteFile:
        """Poll until a terminal status; raise UploadError on timeout or failure."""
        ...

    def detach(self, store_id: str, file_id: str) -> None:
        """Store-scoped detach only. Never calls the global Files delete."""
        ...

    def counts(self, store_id: str) -> StoreCounts:
        """Observed provider file counts for the store."""
        ...


class Publisher(Protocol):
    """Public run-artifact edge (approved method: public GitHub Gist)."""

    def publish(self, payload: str) -> str:
        """Publish the JSON payload; return its public URL. Raise PublishError on failure."""
        ...
