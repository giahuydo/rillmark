"""Offline contract checks for the OpenAI vector-store gateway."""

import json
import socket
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import SimpleNamespace

import httpx2
import pytest
from openai import OpenAI

from rillmark.errors import RemoteStateError, StoreResolutionError, UploadError
from rillmark.models import MANAGED_BY, STORE_NAME, ArticleDoc, ChunkConfig, FileStatus, StoreCounts
from rillmark.vector_store import OpenAIStoreGateway


def obj(**kwargs: object) -> SimpleNamespace:
    """Build an SDK-shaped response without calling the provider."""
    return SimpleNamespace(**kwargs)


class FakePage:
    """Simulate SDK cursor iteration, including errors on later pages."""

    def __init__(self, pages: list[list[object]], fail_page: int | None = None) -> None:
        self.pages = pages
        self.fail_page = fail_page
        self.visited: list[int] = []

    def __iter__(self) -> Iterator[object]:
        for index, page in enumerate(self.pages):
            self.visited.append(index)
            if index == self.fail_page:
                raise RuntimeError("page unavailable")
            yield from page


class FakeStoreFiles:
    def __init__(self) -> None:
        self.pages: list[list[object]] = [[]]
        self.fail_page: int | None = None
        self.retrieved: dict[str, object] = {}
        self.poll: list[object] = []
        self.created: list[dict[str, object]] = []
        self.deleted: list[tuple[str, str]] = []
        self.fail_list = False
        self.fail_attach = False
        self.fail_detach = False
        self.last_page: FakePage | None = None

    def list(self, vector_store_id: str, *, timeout: float) -> FakePage:
        assert vector_store_id == "vs-owned"
        assert timeout > 0
        if self.fail_list:
            raise RuntimeError("listing unavailable")
        self.last_page = FakePage(self.pages, self.fail_page)
        return self.last_page

    def retrieve(self, file_id: str, *, vector_store_id: str, timeout: float) -> object:
        assert vector_store_id == "vs-owned"
        assert timeout > 0
        if self.poll:
            return self.poll.pop(0)
        return self.retrieved[file_id]

    def create(self, vector_store_id: str, **kwargs: object) -> object:
        assert vector_store_id == "vs-owned"
        self.created.append(kwargs)
        if self.fail_attach:
            raise RuntimeError("attach error")
        return obj(
            id=kwargs["file_id"],
            status="in_progress",
            attributes=kwargs["attributes"],
            created_at=4,
        )

    def delete(self, file_id: str, *, vector_store_id: str, timeout: float) -> object:
        assert timeout > 0
        self.deleted.append((vector_store_id, file_id))
        return obj(deleted=not self.fail_detach)


class FakeStores:
    def __init__(self) -> None:
        self.pages: list[list[object]] = [[]]
        self.fail_page: int | None = None
        self.created: list[dict[str, object]] = []
        self.explicit: object = store("vs-owned", MANAGED_BY)
        self.files = FakeStoreFiles()

    def list(self, *, timeout: float) -> FakePage:
        assert timeout > 0
        return FakePage(self.pages, self.fail_page)

    def retrieve(self, vector_store_id: str, *, timeout: float) -> object:
        assert timeout > 0
        if isinstance(self.explicit, Exception):
            raise self.explicit
        return self.explicit

    def create(self, **kwargs: object) -> object:
        self.created.append(kwargs)
        return store("vs-owned", MANAGED_BY)


class FakeFiles:
    def __init__(self) -> None:
        self.uploaded: list[dict[str, object]] = []
        self.global_deletes: list[str] = []
        self.fail_upload = False

    def create(self, **kwargs: object) -> object:
        self.uploaded.append(kwargs)
        if self.fail_upload:
            raise RuntimeError("upload error")
        return obj(id="file-new")

    def delete(self, file_id: str) -> None:
        self.global_deletes.append(file_id)


@dataclass
class FakeClient:
    vector_stores: FakeStores
    files: FakeFiles


def client() -> FakeClient:
    """Provide an isolated in-memory client."""
    return FakeClient(FakeStores(), FakeFiles())


def store(identifier: str, marker: str | None) -> SimpleNamespace:
    """Provide a vector store with an optional ownership marker."""
    return obj(
        id=identifier,
        name=STORE_NAME,
        metadata={"managed_by": marker} if marker else None,
        file_counts=obj(total=4, completed=3),
    )


def attachment(identifier: str, attributes: Mapping[str, str] | None = None) -> SimpleNamespace:
    """Provide an SDK-shaped attachment."""
    return obj(id=identifier, status="completed", attributes=attributes, created_at=10)


def doc() -> ArticleDoc:
    """Provide a minimal generated article file."""
    return ArticleDoc(
        7, 1, "sample", "Sample", "https://example.org/7", 2, "2026-01-01", "# Sample\n", 4
    )


def test_resolve_creates_only_after_all_pages_contain_no_marker() -> None:
    fake = client()
    fake.vector_stores.pages = [[store("vs-foreign", None)], [store("vs-other", "other")]]

    result = OpenAIStoreGateway(fake).resolve_store(None)

    assert result == "vs-owned"
    assert fake.vector_stores.created == [
        {"name": STORE_NAME, "metadata": {"managed_by": MANAGED_BY}, "timeout": 30.0}
    ]


def test_resolve_reuses_marker_on_later_page_ignoring_matching_name() -> None:
    fake = client()
    fake.vector_stores.pages = [[store("vs-foreign", None)], [store("vs-owned", MANAGED_BY)]]

    assert OpenAIStoreGateway(fake).resolve_store(None) == "vs-owned"
    assert fake.vector_stores.created == []


def test_resolve_rejects_ambiguous_marked_stores() -> None:
    fake = client()
    fake.vector_stores.pages = [[store("one", MANAGED_BY)], [store("two", MANAGED_BY)]]

    with pytest.raises(StoreResolutionError):
        OpenAIStoreGateway(fake).resolve_store(None)
    assert fake.vector_stores.created == []


@pytest.mark.parametrize("marked", [True, False])
def test_resolve_explicit_checks_marker(marked: bool) -> None:
    fake = client()
    fake.vector_stores.explicit = store("vs-owned", MANAGED_BY if marked else None)

    if marked:
        assert OpenAIStoreGateway(fake).resolve_store("vs-owned") == "vs-owned"
    else:
        with pytest.raises(StoreResolutionError):
            OpenAIStoreGateway(fake).resolve_store("vs-owned")
    assert fake.vector_stores.created == []


def test_resolve_explicit_retrieval_error_fails_closed() -> None:
    fake = client()
    fake.vector_stores.explicit = RuntimeError("not found")

    with pytest.raises(StoreResolutionError):
        OpenAIStoreGateway(fake).resolve_store("missing")


def test_resolve_page_error_never_creates() -> None:
    fake = client()
    fake.vector_stores.pages = [[store("foreign", None)], [store("vs-owned", MANAGED_BY)]]
    fake.vector_stores.fail_page = 1

    with pytest.raises(StoreResolutionError):
        OpenAIStoreGateway(fake).resolve_store(None)
    assert fake.vector_stores.created == []


def test_list_files_reads_all_pages_and_retrieves_missing_attributes() -> None:
    fake = client()
    fake.vector_stores.files.pages = [
        [attachment("one", {"managed_by": MANAGED_BY})],
        [attachment("two", None)],
    ]
    fake.vector_stores.files.retrieved["two"] = attachment("two", {"managed_by": "foreign"})

    result = OpenAIStoreGateway(fake).list_files("vs-owned")

    assert [entry.file_id for entry in result] == ["one", "two"]
    assert result[0].status is FileStatus.COMPLETED
    assert result[1].attributes == {"managed_by": "foreign"}


@pytest.mark.parametrize("fail_page", [0, 1])
def test_list_files_page_error_never_returns_partial_state(fail_page: int) -> None:
    fake = client()
    fake.vector_stores.files.pages = [[attachment("one", {})], [attachment("two", {})]]
    fake.vector_stores.files.fail_page = fail_page

    with pytest.raises(RemoteStateError) as caught:
        OpenAIStoreGateway(fake).list_files("vs-owned")
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert str(caught.value.__cause__) == "page unavailable"
    assert fake.vector_stores.files.last_page is not None
    assert fake.vector_stores.files.last_page.visited == list(range(fail_page + 1))


def test_list_files_retrieve_error_never_returns_partial_state() -> None:
    fake = client()
    fake.vector_stores.files.pages = [[attachment("missing")]]

    with pytest.raises(RemoteStateError):
        OpenAIStoreGateway(fake).list_files("vs-owned")


def test_upload_uses_filename_attributes_and_static_chunking() -> None:
    fake = client()
    attributes = {"managed_by": MANAGED_BY, "article_id": "7"}

    result = OpenAIStoreGateway(fake).upload("vs-owned", doc(), attributes, ChunkConfig(800, 100))

    assert fake.files.uploaded == [
        {"purpose": "assistants", "file": ("sample.md", b"# Sample\n"), "timeout": 30.0}
    ]
    assert fake.vector_stores.files.created == [
        {
            "file_id": "file-new",
            "attributes": attributes,
            "chunking_strategy": {
                "type": "static",
                "static": {"max_chunk_size_tokens": 800, "chunk_overlap_tokens": 100},
            },
            "timeout": 30.0,
        }
    ]
    assert result.file_id == "file-new"


def test_upload_errors_are_wrapped() -> None:
    fake = client()
    fake.files.fail_upload = True

    with pytest.raises(UploadError):
        OpenAIStoreGateway(fake).upload("vs-owned", doc(), {}, ChunkConfig(800, 100))


def test_upload_attach_error_never_globally_deletes_orphan_file() -> None:
    fake = client()
    fake.vector_stores.files.fail_attach = True

    with pytest.raises(UploadError):
        OpenAIStoreGateway(fake).upload("vs-owned", doc(), {}, ChunkConfig(800, 100))

    assert fake.files.global_deletes == []


@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
def test_poll_terminal_status(terminal: str) -> None:
    fake = client()
    fake.vector_stores.files.poll = [
        obj(id="new", status="in_progress", attributes={}, created_at=4),
        obj(id="new", status=terminal, attributes={}, created_at=4),
    ]
    elapsed = [0.0]
    delays: list[float] = []

    def sleep(delay: float) -> None:
        delays.append(delay)
        elapsed[0] += delay

    gateway = OpenAIStoreGateway(fake, sleep=sleep, clock=lambda: elapsed[0])
    if terminal == "completed":
        assert gateway.wait_completed("vs-owned", "new", 10).status is FileStatus.COMPLETED
    else:
        with pytest.raises(UploadError):
            gateway.wait_completed("vs-owned", "new", 10)
    assert delays and 0 < delays[0] <= 10


def test_poll_timeout_is_bounded() -> None:
    fake = client()
    fake.vector_stores.files.poll = [
        obj(id="new", status="in_progress", attributes={}, created_at=4)
    ] * 10
    elapsed = [0.0]

    def sleep(delay: float) -> None:
        elapsed[0] += delay

    with pytest.raises(UploadError, match="timed out"):
        OpenAIStoreGateway(fake, sleep=sleep, clock=lambda: elapsed[0]).wait_completed(
            "vs-owned", "new", 2
        )
    assert elapsed[0] == 2


def test_detach_failure_is_reported_without_global_delete() -> None:
    fake = client()
    fake.vector_stores.files.fail_detach = True

    with pytest.raises(UploadError):
        OpenAIStoreGateway(fake).detach("vs-owned", "file-old")

    assert fake.files.global_deletes == []


def test_detach_only_uses_store_scoped_delete() -> None:
    fake = client()

    OpenAIStoreGateway(fake).detach("vs-owned", "file-old")

    assert fake.vector_stores.files.deleted == [("vs-owned", "file-old")]
    assert fake.files.global_deletes == []


def test_counts_list_failure_is_not_a_zero_managed_count() -> None:
    fake = client()
    fake.vector_stores.files.fail_list = True

    with pytest.raises(RemoteStateError):
        OpenAIStoreGateway(fake).counts("vs-owned")


def test_confirmed_null_attributes_remain_unowned() -> None:
    fake = client()
    fake.vector_stores.files.pages = [[attachment("manual", None)]]
    fake.vector_stores.files.retrieved["manual"] = attachment("manual", None)

    result = OpenAIStoreGateway(fake).list_files("vs-owned")

    assert result[0].attributes == {}
    assert not result[0].managed


def test_retrieval_without_attributes_field_fails_closed() -> None:
    fake = client()
    fake.vector_stores.files.pages = [[attachment("manual", None)]]
    fake.vector_stores.files.retrieved["manual"] = obj(
        id="manual", status="completed", created_at=1
    )

    with pytest.raises(RemoteStateError):
        OpenAIStoreGateway(fake).list_files("vs-owned")


def test_counts_uses_store_counts_and_completed_managed_files() -> None:
    fake = client()
    fake.vector_stores.files.pages = [
        [attachment("own", {"managed_by": MANAGED_BY})],
        [attachment("other", {"managed_by": "other"})],
    ]

    result = OpenAIStoreGateway(fake).counts("vs-owned")

    assert result == StoreCounts(files_in_store=4, files_completed=3, managed_files_completed=1)
    assert fake.files.global_deletes == []


# Pinned SDK + in-memory HTTP transport catches signature and cursor differences
# that a Python-only fake cannot exercise. The transport never opens a socket.
def sdk_store(identifier: str = "vs-owned", marker: str | None = MANAGED_BY) -> dict[str, object]:
    """Build a valid SDK vector-store payload."""
    return {
        "id": identifier,
        "object": "vector_store",
        "created_at": 1,
        "name": "same-display-name",
        "metadata": {"managed_by": marker} if marker else {},
        "status": "completed",
        "usage_bytes": 0,
        "file_counts": {"total": 2, "completed": 2, "in_progress": 0, "failed": 0, "cancelled": 0},
    }


def sdk_attachment(
    identifier: str = "file-old",
    attributes: dict[str, str | int] | None = None,
    status: str = "completed",
) -> dict[str, object]:
    """Build a valid SDK vector-store attachment payload."""
    return {
        "id": identifier,
        "object": "vector_store.file",
        "created_at": 1,
        "usage_bytes": 0,
        "vector_store_id": "vs-owned",
        "status": status,
        "attributes": attributes,
    }


def sdk_client(handler: Callable[[httpx2.Request], httpx2.Response]) -> OpenAI:
    """Construct a real SDK client backed solely by a mock HTTP transport."""
    return OpenAI(
        api_key="test-placeholder",
        base_url="https://offline.invalid/v1",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


@pytest.fixture
def no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately if a real-SDK test attempts a network connection."""

    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network access forbidden by vector-store tests")

    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.mark.usefixtures("no_socket")
@pytest.mark.parametrize("marked_count", [0, 1, 2])
def test_real_sdk_resolves_across_cursor_pages(marked_count: int) -> None:
    calls: list[tuple[str, str, dict[str, str]]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append((request.method, request.url.path, dict(request.url.params)))
        if request.method == "GET":
            if not request.url.params.get("after"):
                return httpx2.Response(
                    200, json={"data": [sdk_store("vs-foreign", None)], "has_more": True}
                )
            return httpx2.Response(
                200,
                json={
                    "data": [sdk_store(f"vs-{index}") for index in range(marked_count)],
                    "has_more": False,
                },
            )
        body = json.loads(request.content)
        assert body["metadata"] == {"managed_by": MANAGED_BY}
        assert "expires_after" not in body
        return httpx2.Response(200, json=sdk_store("vs-created"))

    with sdk_client(handler) as openai_client:
        gateway = OpenAIStoreGateway(openai_client)
        if marked_count > 1:
            with pytest.raises(StoreResolutionError):
                gateway.resolve_store(None)
        else:
            assert gateway.resolve_store(None) == ("vs-created" if marked_count == 0 else "vs-0")
    assert calls[1][2]["after"] == "vs-foreign"
    assert sum(method == "POST" for method, _, _ in calls) == (marked_count == 0)


@pytest.mark.usefixtures("no_socket")
@pytest.mark.parametrize("marker", [MANAGED_BY, "foreign"])
def test_real_sdk_explicit_store_requires_marker(marker: str) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/vector_stores/vs-owned"
        return httpx2.Response(200, json=sdk_store(marker=marker))

    with sdk_client(handler) as openai_client:
        if marker == MANAGED_BY:
            assert OpenAIStoreGateway(openai_client).resolve_store("vs-owned") == "vs-owned"
        else:
            with pytest.raises(StoreResolutionError):
                OpenAIStoreGateway(openai_client).resolve_store("vs-owned")


@pytest.mark.usefixtures("no_socket")
def test_real_sdk_upload_list_poll_counts_and_detach() -> None:
    calls: list[tuple[str, str]] = []
    attributes = {"managed_by": MANAGED_BY, "article_id": "7", "part": 1}

    def handler(request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        calls.append((request.method, path))
        if path == "/v1/files" and request.method == "POST":
            body = request.read()
            assert b'filename="sample.md"' in body
            assert b"assistants" in body and b"# Sample\n" in body
            return httpx2.Response(
                200,
                json={
                    "id": "file-new",
                    "object": "file",
                    "filename": "sample.md",
                    "purpose": "assistants",
                    "bytes": 9,
                    "created_at": 1,
                },
            )
        if path == "/v1/vector_stores/vs-owned/files" and request.method == "POST":
            body = json.loads(request.content)
            assert body["file_id"] == "file-new" and body["attributes"] == attributes
            assert body["chunking_strategy"] == {
                "type": "static",
                "static": {"max_chunk_size_tokens": 800, "chunk_overlap_tokens": 100},
            }
            return httpx2.Response(200, json=sdk_attachment("file-new", attributes, "in_progress"))
        if path == "/v1/vector_stores/vs-owned/files" and request.method == "GET":
            if not request.url.params.get("after"):
                return httpx2.Response(
                    200, json={"data": [sdk_attachment(attributes=attributes)], "has_more": True}
                )
            assert request.url.params["after"] == "file-old"
            item = sdk_attachment("file-manual")
            item.pop("attributes")
            return httpx2.Response(200, json={"data": [item], "has_more": False})
        if path == "/v1/vector_stores/vs-owned/files/file-manual" and request.method == "GET":
            return httpx2.Response(200, json=sdk_attachment("file-manual", {}))
        if path == "/v1/vector_stores/vs-owned/files/file-new" and request.method == "GET":
            return httpx2.Response(200, json=sdk_attachment("file-new", attributes))
        if path == "/v1/vector_stores/vs-owned/files/file-old" and request.method == "DELETE":
            return httpx2.Response(
                200, json={"id": "file-old", "deleted": True, "object": "vector_store.file.deleted"}
            )
        if path == "/v1/vector_stores/vs-owned" and request.method == "GET":
            return httpx2.Response(200, json=sdk_store())
        raise AssertionError((request.method, path))

    with sdk_client(handler) as openai_client:
        gateway = OpenAIStoreGateway(openai_client)
        assert gateway.upload("vs-owned", doc(), attributes, ChunkConfig(800, 100)).status is (
            FileStatus.IN_PROGRESS
        )
        files = gateway.list_files("vs-owned")
        assert [entry.file_id for entry in files] == ["file-old", "file-manual"]
        assert files[0].managed and not files[1].managed
        assert gateway.wait_completed("vs-owned", "file-new", 1).status is FileStatus.COMPLETED
        assert gateway.counts("vs-owned") == StoreCounts(2, 2, 1)
        gateway.detach("vs-owned", "file-old")
    assert ("DELETE", "/v1/files/file-old") not in calls
    assert ("DELETE", "/v1/vector_stores/vs-owned/files/file-old") in calls


@pytest.mark.usefixtures("no_socket")
def test_real_sdk_later_file_page_error_is_remote_state_error() -> None:
    pages: list[dict[str, str]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        pages.append(dict(request.url.params))
        if not request.url.params.get("after"):
            return httpx2.Response(
                200, json={"data": [sdk_attachment(attributes={})], "has_more": True}
            )
        return httpx2.Response(
            500, json={"error": {"message": "later page unavailable", "type": "server_error"}}
        )

    with sdk_client(handler) as openai_client, pytest.raises(RemoteStateError):
        OpenAIStoreGateway(openai_client).list_files("vs-owned")
    assert len(pages) == 2 and pages[1]["after"] == "file-old"


@pytest.mark.usefixtures("no_socket")
def test_real_sdk_explicit_null_attributes_are_valid_unowned_attachment() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        item = sdk_attachment("file-manual")
        if request.url.path.endswith("/files"):
            return httpx2.Response(200, json={"data": [item], "has_more": False})
        return httpx2.Response(200, json=item)

    with sdk_client(handler) as openai_client:
        result = OpenAIStoreGateway(openai_client).list_files("vs-owned")
    assert len(result) == 1 and result[0].file_id == "file-manual"
    assert result[0].attributes == {} and not result[0].managed


def test_completed_response_after_deadline_is_still_timeout() -> None:
    elapsed = [0.0]

    def retrieve(*args: object, **kwargs: object) -> SimpleNamespace:
        assert kwargs["timeout"] == 1.0
        elapsed[0] += 2.0
        return obj(id="file-new", status="completed", attributes={}, created_at=1)

    fake = obj(vector_stores=obj(files=obj(retrieve=retrieve)))
    gateway = OpenAIStoreGateway(fake, clock=lambda: elapsed[0], sleep=lambda delay: None)
    with pytest.raises(UploadError, match="timed out"):
        gateway.wait_completed("vs-owned", "file-new", 1.0)
