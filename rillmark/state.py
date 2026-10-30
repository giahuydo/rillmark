"""Pure hashing, attachment attributes, and delta planning."""

from collections.abc import Sequence
from hashlib import sha256 as hash_sha256

from rillmark.models import (
    MANAGED_BY,
    SCHEMA_VERSION,
    ArticleDoc,
    ChunkConfig,
    DeltaPlan,
    FileStatus,
    RemoteFile,
    Replacement,
)


def content_hash(markdown: str, chunk: ChunkConfig, schema_version: int = SCHEMA_VERSION) -> str:
    """Return the versioned SHA-256 digest of the supplied Markdown."""
    prefix = f"v{schema_version}\nchunk={chunk.max_tokens}/{chunk.overlap_tokens}\n"
    return hash_sha256((prefix + markdown).encode("utf-8")).hexdigest()


def file_attributes(doc: ArticleDoc, sha256: str) -> dict[str, str | int]:
    """Return the owned attachment attributes required by docs/02 §4."""
    return {
        "managed_by": MANAGED_BY,
        "article_id": str(doc.article_id),
        "sha256": sha256,
        "url": doc.url,
        "slug": doc.slug,
        "part": doc.part,
        "section_id": str(doc.section_id),
        "source_updated_at": doc.source_updated_at,
        "schema_version": SCHEMA_VERSION,
    }


def classify(
    desired: Sequence[ArticleDoc], remote: Sequence[RemoteFile], chunk: ChunkConfig
) -> DeltaPlan:
    """Return a deterministic delta plan containing only owned remote files."""
    desired_by_key: dict[str, ArticleDoc] = {}
    for doc in desired:
        if doc.key in desired_by_key:
            raise ValueError(f"Duplicate desired key: {doc.key}")
        desired_by_key[doc.key] = doc
    owned = _group_owned(remote)
    plans = [
        _classify_doc(doc, owned.get(key, ()), chunk) for key, doc in sorted(desired_by_key.items())
    ]
    desired_article_ids = {doc.article_id for doc in desired}
    absent_article_ids = {
        int(key.split("/", 1)[0])
        for key, entries in owned.items()
        if any(entry.status == FileStatus.COMPLETED for entry in entries)
    } - desired_article_ids
    return DeltaPlan(
        added=tuple(doc for plan in plans for doc in plan.added),
        updated=tuple(replacement for plan in plans for replacement in plan.updated),
        skipped=tuple(doc for plan in plans for doc in plan.skipped),
        retried=tuple(replacement for plan in plans for replacement in plan.retried),
        deletion_candidates=tuple(sorted(absent_article_ids)),
        duplicates=tuple(entry for plan in plans for entry in plan.duplicates),
    )


def _group_owned(remote: Sequence[RemoteFile]) -> dict[str, list[RemoteFile]]:
    owned: dict[str, list[RemoteFile]] = {}
    for entry in remote:
        key = entry.key
        if key is not None:
            owned.setdefault(key, []).append(entry)
    return owned


def _newest(entries: Sequence[RemoteFile]) -> RemoteFile:
    # Provider listing order is not stable, so equal timestamps need an ID tie-break.
    return max(entries, key=lambda entry: (entry.created_at, entry.file_id))


def _classify_doc(doc: ArticleDoc, entries: Sequence[RemoteFile], chunk: ChunkConfig) -> DeltaPlan:
    completed = [entry for entry in entries if entry.status == FileStatus.COMPLETED]
    if not completed:
        retryable = [
            entry for entry in entries if entry.status in (FileStatus.FAILED, FileStatus.CANCELLED)
        ]
        if retryable:
            return DeltaPlan((), (), (), (Replacement(doc, _newest(retryable)),), (), ())
        return DeltaPlan((doc,), (), (), (), (), ())

    sha256 = content_hash(doc.markdown, chunk)
    matching = [entry for entry in completed if entry.attributes.get("sha256") == sha256]
    kept = _newest(matching or completed)
    duplicates = tuple(
        sorted(
            (entry for entry in completed if entry is not kept),
            key=lambda entry: entry.file_id,
        )
    )
    # Only desired keys produce cleanup entries; source absence stays reporting-only.
    if matching:
        return DeltaPlan((), (), (doc,), (), (), duplicates)
    return DeltaPlan((), (Replacement(doc, kept),), (), (), (), duplicates)
