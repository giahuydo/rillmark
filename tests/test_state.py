"""Offline acceptance checks for docs/03 sections 2-5 and docs/02 section 4."""

from dataclasses import replace

import pytest

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
from rillmark.state import classify, content_hash, file_attributes

CHUNK: ChunkConfig = ChunkConfig(max_tokens=800, overlap_tokens=100)
MARKDOWN: str = "# Café\n\nArticle URL: https://example.test/7\n\nA body.\n"
DIGEST: str = "76c7ac56cce8b0d899e4f912750295e62122088308053cae00c94399605c92fd"


def make_doc(article_id: int = 7, part: int = 1) -> ArticleDoc:
    return ArticleDoc(
        article_id=article_id,
        part=part,
        slug="cafe",
        title="Café",
        url=f"https://example.test/{article_id}",
        section_id=12,
        source_updated_at="2026-10-30T00:00:00Z",
        markdown=MARKDOWN,
        tokens=20,
    )


def make_remote(
    doc: ArticleDoc,
    file_id: str = "file-old",
    status: FileStatus = FileStatus.COMPLETED,
    sha256: str = DIGEST,
    created_at: int = 0,
) -> RemoteFile:
    return RemoteFile(
        file_id=file_id,
        status=status,
        attributes={
            "managed_by": MANAGED_BY,
            "article_id": str(doc.article_id),
            "part": doc.part,
            "sha256": sha256,
        },
        created_at=created_at,
    )


def test_content_hash_matches_versioned_utf8_sha256() -> None:
    assert content_hash(MARKDOWN, CHUNK) == DIGEST
    assert content_hash(MARKDOWN, CHUNK, schema_version=1) == DIGEST


@pytest.mark.parametrize(
    ("chunk", "schema_version"),
    [(ChunkConfig(801, 100), 1), (ChunkConfig(800, 101), 1), (CHUNK, 2)],
)
def test_content_hash_changes_with_chunk_or_schema(chunk: ChunkConfig, schema_version: int) -> None:
    assert content_hash(MARKDOWN, chunk, schema_version) != DIGEST


@pytest.mark.parametrize("suffix", ["More content.\n", "\n", " ", "\u200b"])
def test_content_hash_preserves_supplied_markdown_bytes(suffix: str) -> None:
    assert content_hash(MARKDOWN + suffix, CHUNK) != DIGEST


@pytest.mark.parametrize("part", [1, 2])
def test_file_attributes_matches_exact_attachment_contract(part: int) -> None:
    doc = make_doc(part=part)

    attributes = file_attributes(doc, DIGEST)

    assert attributes == {
        "managed_by": MANAGED_BY,
        "article_id": "7",
        "sha256": DIGEST,
        "url": "https://example.test/7",
        "slug": "cafe",
        "part": part,
        "section_id": "12",
        "source_updated_at": "2026-10-30T00:00:00Z",
        "schema_version": SCHEMA_VERSION,
    }
    assert type(attributes["part"]) is int
    assert type(attributes["schema_version"]) is int


@pytest.mark.parametrize(
    ("status", "sha256", "category"),
    [
        (None, DIGEST, "added"),
        (FileStatus.COMPLETED, DIGEST, "skipped"),
        (FileStatus.COMPLETED, "older-content", "updated"),
        (FileStatus.FAILED, DIGEST, "retried"),
        (FileStatus.CANCELLED, DIGEST, "retried"),
        (FileStatus.IN_PROGRESS, DIGEST, "added"),
    ],
)
def test_classify_maps_desired_remote_state_to_delta(
    status: FileStatus | None, sha256: str, category: str
) -> None:
    doc = make_doc()
    remote = () if status is None else (make_remote(doc, status=status, sha256=sha256),)

    plan = classify((doc,), remote, CHUNK)

    assert plan == DeltaPlan(
        added=(doc,) if category == "added" else (),
        updated=(Replacement(doc, remote[0]),) if category == "updated" else (),
        skipped=(doc,) if category == "skipped" else (),
        retried=(Replacement(doc, remote[0]),) if category == "retried" else (),
        deletion_candidates=(),
        duplicates=(),
    )


@pytest.mark.parametrize("marker", [None, "", "another-owner"])
@pytest.mark.parametrize("status", list(FileStatus))
def test_classify_excludes_foreign_files_from_every_plan_list(
    marker: str | None, status: FileStatus
) -> None:
    doc = make_doc()
    attributes: dict[str, str | int | float | bool] = {
        "article_id": "7",
        "part": "invalid-foreign-part",
        "sha256": DIGEST,
    }
    if marker is not None:
        attributes["managed_by"] = marker
    remote = RemoteFile("file-foreign", status, attributes)
    absent = replace(remote, file_id="file-absent", attributes={**attributes, "article_id": "99"})

    plan = classify((doc,), (remote, absent), CHUNK)

    assert plan == DeltaPlan((doc,), (), (), (), (), ())


def test_classify_uses_hash_instead_of_source_metadata() -> None:
    original = make_doc()
    doc = replace(original, source_updated_at="2026-10-31T00:00:00Z", slug="renamed")

    plan = classify((doc,), (make_remote(original),), CHUNK)

    assert plan == DeltaPlan((), (), (doc,), (), (), ())


def test_classify_updates_when_markdown_changes() -> None:
    original = make_doc()
    changed = replace(original, markdown=MARKDOWN + "A new paragraph.\n")
    old = make_remote(original)

    plan = classify((changed,), (old,), CHUNK)

    assert plan == DeltaPlan((), (Replacement(changed, old),), (), (), (), ())


@pytest.mark.parametrize("chunk", [ChunkConfig(801, 100), ChunkConfig(800, 101)])
def test_classify_updates_when_chunk_settings_change(chunk: ChunkConfig) -> None:
    doc = make_doc()
    old = make_remote(doc)

    plan = classify((doc,), (old,), chunk)

    assert plan == DeltaPlan((), (Replacement(doc, old),), (), (), (), ())


@pytest.mark.parametrize("matching", [True, False])
def test_classify_completed_file_takes_precedence_over_failed_retry(matching: bool) -> None:
    doc = make_doc()
    completed = make_remote(doc, sha256=DIGEST if matching else "old")
    failed = make_remote(doc, "file-failed", FileStatus.FAILED, created_at=100)

    plan = classify((doc,), (failed, completed), CHUNK)

    assert plan == DeltaPlan(
        (),
        () if matching else (Replacement(doc, completed),),
        (doc,) if matching else (),
        (),
        (),
        (),
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_classify_retries_newest_failed_or_cancelled_entry(reverse: bool) -> None:
    doc = make_doc()
    failed = make_remote(doc, "file-failed", FileStatus.FAILED, created_at=10)
    cancelled = make_remote(doc, "file-cancelled", FileStatus.CANCELLED, created_at=20)
    pending = make_remote(doc, "file-pending", FileStatus.IN_PROGRESS, created_at=30)
    remote = [failed, cancelled, pending]

    plan = classify((doc,), remote[::-1] if reverse else remote, CHUNK)

    assert plan == DeltaPlan((), (), (), (Replacement(doc, cancelled),), (), ())


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize(
    ("hashes", "times", "kept"),
    [
        ((DIGEST, "old", "old"), (1, 2, 3), 0),
        (("old", "old", "old"), (3, 1, 2), 0),
        ((DIGEST, "old", DIGEST), (1, 3, 2), 2),
        ((DIGEST, DIGEST, DIGEST), (1, 1, 1), 2),
        (("old", "old", "old"), (1, 1, 1), 2),
    ],
)
def test_classify_resolves_duplicates_by_hash_then_newest_with_stable_ties(
    hashes: tuple[str, ...], times: tuple[int, ...], kept: int, reverse: bool
) -> None:
    doc = make_doc()
    remote = [
        make_remote(doc, f"file-{index}", sha256=sha256, created_at=created_at)
        for index, (sha256, created_at) in enumerate(zip(hashes, times, strict=True))
    ]
    matching = hashes[kept] == DIGEST

    plan = classify((doc,), remote[::-1] if reverse else remote, CHUNK)

    assert plan == DeltaPlan(
        (),
        () if matching else (Replacement(doc, remote[kept]),),
        (doc,) if matching else (),
        (),
        (),
        tuple(entry for index, entry in enumerate(remote) if index != kept),
    )


def test_classify_reports_sorted_unique_absent_articles_including_split_parts() -> None:
    doc = make_doc()
    remote = (
        make_remote(make_doc(10), "file-10"),
        make_remote(make_doc(9, 2), "file-9-part-2"),
        make_remote(make_doc(9), "file-9-part-1"),
        make_remote(make_doc(7, 2), "file-present-article-part-2"),
        make_remote(make_doc(11), "file-failed", FileStatus.FAILED),
        make_remote(make_doc(12), "file-cancelled", FileStatus.CANCELLED),
        make_remote(make_doc(13), "file-pending", FileStatus.IN_PROGRESS),
    )

    plan = classify((doc,), remote, CHUNK)

    assert plan == DeltaPlan((doc,), (), (), (), (9, 10), ())


def test_classify_preserves_absent_article_duplicates_as_reporting_only() -> None:
    doc = make_doc()
    remote = (make_remote(doc, "file-a"), make_remote(doc, "file-b", created_at=1))

    plan = classify((), remote, CHUNK)

    assert plan == DeltaPlan((), (), (), (), (7,), ())


def test_classify_returns_empty_plan_for_empty_inputs() -> None:
    assert classify((), (), CHUNK) == DeltaPlan((), (), (), (), (), ())


@pytest.mark.parametrize("changed_content", [False, True])
def test_classify_rejects_duplicate_desired_keys(changed_content: bool) -> None:
    doc = make_doc()
    duplicate = replace(doc, markdown="different") if changed_content else doc

    with pytest.raises(ValueError):
        classify((doc, duplicate), (), CHUNK)


@pytest.mark.parametrize("reverse_desired", [False, True])
@pytest.mark.parametrize("reverse_remote", [False, True])
def test_classify_orders_each_category_by_canonical_key_without_mutating_inputs(
    reverse_desired: bool, reverse_remote: bool
) -> None:
    added = (make_doc(10), make_doc(2))
    skipped = (make_doc(30), make_doc(30, 2))
    updated = (make_doc(40), make_doc(40, 2))
    retried = (make_doc(50), make_doc(50, 2))
    old = tuple(make_remote(doc, f"file-{doc.key}", sha256="old") for doc in updated)
    failed = tuple(make_remote(doc, f"file-{doc.key}", FileStatus.FAILED) for doc in retried)
    duplicates = tuple(
        make_remote(doc, f"surplus-{doc.key}", sha256="old", created_at=-1) for doc in updated
    )
    desired = list(added + skipped + updated + retried)
    remote = [
        *(make_remote(doc, f"file-{doc.key}") for doc in skipped),
        *old,
        *failed,
        *duplicates,
        make_remote(make_doc(100), "file-absent"),
    ]
    if reverse_desired:
        desired.reverse()
    if reverse_remote:
        remote.reverse()
    original_desired = desired.copy()
    original_remote = remote.copy()
    original_attributes = [dict(entry.attributes) for entry in remote]

    plan = classify(desired, remote, CHUNK)

    assert plan == DeltaPlan(
        added,
        tuple(Replacement(doc, entry) for doc, entry in zip(updated, old, strict=True)),
        skipped,
        tuple(Replacement(doc, entry) for doc, entry in zip(retried, failed, strict=True)),
        (100,),
        duplicates,
    )
    assert desired == original_desired
    assert remote == original_remote
    assert [dict(entry.attributes) for entry in remote] == original_attributes
