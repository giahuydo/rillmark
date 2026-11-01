"""Offline end-to-end runs of rillmark.cli with fake Zendesk, store, and publisher."""

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from rillmark.cli import Deps, pilot_subset, run
from rillmark.errors import PublishError, StoreResolutionError, UploadError
from rillmark.models import (
    MANAGED_BY,
    ArticleDoc,
    ChunkConfig,
    FileStatus,
    RemoteFile,
    StoreCounts,
)

SELECTION = Path(__file__).resolve().parents[1] / "config" / "selection.json"
SECTIONS = json.loads(SELECTION.read_text())["section_ids"]
YOUTUBE_ID = 360051014713
BASE = "https://support.optisigns.com"


def article(article_id: int, section: int, body: str = "<p>Steps.</p>") -> dict:
    return {
        "id": article_id,
        "title": f"Article {article_id}",
        "body": body,
        "html_url": f"{BASE}/hc/en-us/articles/{article_id}",
        "section_id": section,
        "locale": "en-us",
        "draft": False,
        "updated_at": "2026-10-30T00:00:00Z",
    }


def catalog(overrides: Mapping[int, str] | None = None) -> list[dict]:
    items = [article(YOUTUBE_ID, SECTIONS[0], "<p>Add a YouTube video.</p>")]
    items += [article(1000 + i, SECTIONS[i % len(SECTIONS)]) for i in range(31)]
    items.append(article(2000, 999))  # outside the selection
    for article_id, body in (overrides or {}).items():
        for item in items:
            if item["id"] == article_id:
                item["body"] = body
    return items


def fake_zendesk(items: list[dict]):
    def get_json(url: str) -> dict:
        return {"articles": items, "next_page": None}

    return get_json


class FakeStore:
    """In-memory StoreGateway that keeps attachments across runs."""

    def __init__(self, fail_upload: set[int] | None = None, resolve_error: bool = False) -> None:
        self.files: dict[str, RemoteFile] = {}
        self.fail_upload = fail_upload or set()
        self.resolve_error = resolve_error
        self.detached: list[str] = []
        self.uploads: list[int] = []
        self._next = 0

    def resolve_store(self, explicit_id: str | None) -> str:
        if self.resolve_error:
            raise StoreResolutionError("ambiguous")
        return "vs_test"

    def list_files(self, store_id: str) -> list[RemoteFile]:
        return list(self.files.values())

    def upload(self, store_id, doc: ArticleDoc, attributes, chunk: ChunkConfig) -> RemoteFile:
        if doc.article_id in self.fail_upload:
            raise UploadError("boom")
        self._next += 1
        self.uploads.append(doc.article_id)
        file = RemoteFile(
            f"file-{self._next:03d}", FileStatus.IN_PROGRESS, dict(attributes), self._next
        )
        self.files[file.file_id] = file
        return file

    def wait_completed(self, store_id: str, file_id: str, timeout_s: float) -> RemoteFile:
        done = replace(self.files[file_id], status=FileStatus.COMPLETED)
        self.files[file_id] = done
        return done

    def detach(self, store_id: str, file_id: str) -> None:
        self.detached.append(file_id)
        del self.files[file_id]

    def counts(self, store_id: str) -> StoreCounts:
        done = [f for f in self.files.values() if f.status == FileStatus.COMPLETED]
        managed = [f for f in done if f.attributes.get("managed_by") == MANAGED_BY]
        return StoreCounts(len(self.files), len(done), len(managed))


class FakePublisher:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.payloads: list[str] = []

    def publish(self, payload: str) -> str:
        if self.fail:
            raise PublishError("gist down")
        self.payloads.append(payload)
        return "https://gist.github.com/example"


def deps(tmp_path: Path, items, store: FakeStore | None = None, publisher=None, calls=None) -> Deps:
    def gateway_factory(api_key: str):
        if calls is not None:
            calls.append(api_key)
        assert store is not None, "gateway must not be created"
        return store

    return Deps(
        get_json=fake_zendesk(items),
        gateway_factory=gateway_factory,
        publisher_factory=lambda config: publisher,
        now=lambda: "2026-10-31T00:00:00Z",
        selection_path=SELECTION,
        out_dir=tmp_path / "out",
        report_path=tmp_path / "last_run.json",
    )


def last_run(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "last_run.json").read_text())


ENV = {"API_KEY": "test-key"}


def test_dry_run_writes_markdown_without_creating_a_gateway(tmp_path: Path) -> None:
    calls: list[str] = []
    code = run(["--dry-run"], {}, deps(tmp_path, catalog(), calls=calls))
    doc = last_run(tmp_path)
    assert code == 0
    assert calls == []
    assert len(list((tmp_path / "out").glob("*.md"))) == 32
    assert doc["mode"] == "dry-run"
    assert doc["publish"] == "skipped"
    assert doc["counts"]["selected"] == 32
    assert doc["chunks"]["estimated"] == 32
    assert doc["store"]["files_in_store"] is None
    assert doc["chunks"]["actual"] is None


def test_sync_adds_all_then_second_run_skips_all(tmp_path: Path) -> None:
    store = FakeStore()
    assert run([], ENV, deps(tmp_path, catalog(), store)) == 0
    first = last_run(tmp_path)
    assert first["counts"]["added"] == 32
    assert first["status"] == "success"
    assert first["files"]["actual"] == 32
    assert first["publish"] == "skipped"
    assert first["counts"]["selected"] == 32
    assert first["chunks"]["estimated"] == 32

    assert run([], ENV, deps(tmp_path, catalog(), store)) == 0
    second = last_run(tmp_path)
    assert (second["counts"]["added"], second["counts"]["skipped"]) == (0, 32)
    assert store.detached == []


def test_changed_article_is_replaced_and_old_attachment_detached(tmp_path: Path) -> None:
    store = FakeStore()
    run([], ENV, deps(tmp_path, catalog(), store))
    old_ids = {f.file_id for f in store.files.values() if f.attributes["article_id"] == "1005"}

    code = run([], ENV, deps(tmp_path, catalog({1005: "<p>New steps.</p>"}), store))
    doc = last_run(tmp_path)
    assert code == 0
    assert (doc["counts"]["updated"], doc["counts"]["deleted"]) == (1, 1)
    assert set(store.detached) == old_ids
    assert len(store.files) == 32


def test_source_absent_article_is_reported_not_deleted(tmp_path: Path) -> None:
    store = FakeStore()
    run([], ENV, deps(tmp_path, catalog(), store))
    kept = {f.file_id for f in store.files.values() if f.attributes["article_id"] == "1005"}
    shrunk = [a for a in catalog() if a["id"] != 1005]
    assert run([], ENV, deps(tmp_path, shrunk, store)) == 0
    doc = last_run(tmp_path)
    assert doc["deletion_candidates"] == {"count": 1, "article_ids": [1005]}
    counts = doc["counts"]
    assert (counts["added"], counts["updated"], counts["skipped"], counts["deleted"]) == (
        0,
        0,
        31,
        0,
    )
    assert store.detached == []
    assert kept and kept <= set(store.files)


def test_new_article_is_the_only_upload(tmp_path: Path) -> None:
    store = FakeStore()
    run([], ENV, deps(tmp_path, [a for a in catalog() if a["id"] != 1005], store))
    store.uploads.clear()

    assert run([], ENV, deps(tmp_path, catalog(), store)) == 0
    counts = last_run(tmp_path)["counts"]
    assert (counts["added"], counts["updated"], counts["skipped"], counts["deleted"]) == (
        1,
        0,
        31,
        0,
    )
    assert store.uploads == [1005]
    assert store.detached == []
    assert len(store.files) == 32


def test_unchanged_rerun_uploads_nothing(tmp_path: Path) -> None:
    store = FakeStore()
    run([], ENV, deps(tmp_path, catalog(), store))
    before = set(store.files)
    store.uploads.clear()

    assert run([], ENV, deps(tmp_path, catalog(), store)) == 0
    counts = last_run(tmp_path)["counts"]
    assert (counts["added"], counts["updated"], counts["skipped"]) == (0, 0, 32)
    assert store.uploads == []
    assert store.detached == []
    assert set(store.files) == before


class OrderStore(FakeStore):
    """Record upload, completion and detach events in call order."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.events: list[tuple[str, str]] = []

    def upload(self, store_id, doc: ArticleDoc, attributes, chunk: ChunkConfig) -> RemoteFile:
        file = super().upload(store_id, doc, attributes, chunk)
        self.events.append(("upload", file.file_id))
        return file

    def wait_completed(self, store_id: str, file_id: str, timeout_s: float) -> RemoteFile:
        self.events.append(("completed", file_id))
        return super().wait_completed(store_id, file_id, timeout_s)

    def detach(self, store_id: str, file_id: str) -> None:
        self.events.append(("detach", file_id))
        super().detach(store_id, file_id)


def test_update_detaches_old_only_after_replacement_completes(tmp_path: Path) -> None:
    store = OrderStore()
    run([], ENV, deps(tmp_path, catalog(), store))
    (old,) = [f.file_id for f in store.files.values() if f.attributes["article_id"] == "1005"]
    store.events.clear()

    assert run([], ENV, deps(tmp_path, catalog({1005: "<p>New steps.</p>"}), store)) == 0
    (new,) = [f.file_id for f in store.files.values() if f.attributes["article_id"] == "1005"]
    assert store.events == [("upload", new), ("completed", new), ("detach", old)]
    counts = last_run(tmp_path)["counts"]
    assert (counts["added"], counts["updated"], counts["skipped"], counts["deleted"]) == (
        0,
        1,
        31,
        1,
    )


def test_failed_update_upload_keeps_the_old_version(tmp_path: Path) -> None:
    store = FakeStore()
    run([], ENV, deps(tmp_path, catalog(), store))
    old = {fid: f for fid, f in store.files.items() if f.attributes["article_id"] == "1005"}
    store.fail_upload = {1005}

    code = run([], ENV, deps(tmp_path, catalog({1005: "<p>New steps.</p>"}), store))
    doc = last_run(tmp_path)
    assert code == 1
    assert doc["status"] == "partial_failure"
    assert (doc["counts"]["updated"], doc["counts"]["failed"], doc["counts"]["deleted"]) == (
        0,
        1,
        0,
    )
    assert store.detached == []
    assert {fid: store.files[fid] for fid in old} == old


def test_pilot_uploads_youtube_and_longest_only_and_never_detaches(tmp_path: Path) -> None:
    store = FakeStore()
    items = catalog({1010: "<p>" + "long text " * 300 + "</p>"})
    code = run(["--limit", "2"], ENV, deps(tmp_path, items, store))
    doc = last_run(tmp_path)
    assert code == 0
    assert sorted(store.uploads) == [1010, YOUTUBE_ID]
    assert doc["mode"] == "pilot"
    assert doc["counts"]["selected"] == 32
    assert doc["chunks"]["estimated"] == 2
    assert doc["chunks"]["actual"] is None
    assert store.detached == []


def test_pilot_estimate_remains_subset_when_store_resolution_fails(tmp_path: Path) -> None:
    store = FakeStore(resolve_error=True)
    code = run(["--limit", "2"], ENV, deps(tmp_path, catalog(), store))
    doc = last_run(tmp_path)
    assert code == 1
    assert doc["errors"][0]["stage"] == "resolve_store"
    assert doc["counts"]["selected"] == 32
    assert doc["chunks"]["estimated"] == 2
    assert store.uploads == []


def test_pilot_classifies_source_absence_against_full_selection(tmp_path: Path) -> None:
    store = FakeStore()
    assert run([], ENV, deps(tmp_path, catalog(), store)) == 0

    code = run(["--limit", "2"], ENV, deps(tmp_path, catalog(), store))
    doc = last_run(tmp_path)
    assert code == 0
    assert doc["counts"]["skipped"] == 2
    assert doc["chunks"]["estimated"] == 2
    assert doc["deletion_candidates"] == {"count": 0, "article_ids": []}
    assert store.detached == []


def test_upload_failure_is_partial_and_exits_nonzero(tmp_path: Path) -> None:
    store = FakeStore(fail_upload={1003})
    code = run([], ENV, deps(tmp_path, catalog(), store))
    doc = last_run(tmp_path)
    assert code == 1
    assert doc["status"] == "partial_failure"
    assert (doc["counts"]["added"], doc["counts"]["failed"]) == (31, 1)
    assert doc["errors"][0]["article_id"] == 1003


def test_store_resolution_failure_makes_no_uploads(tmp_path: Path) -> None:
    store = FakeStore(resolve_error=True)
    code = run([], ENV, deps(tmp_path, catalog(), store))
    doc = last_run(tmp_path)
    assert code == 1
    assert doc["status"] == "failed"
    assert store.uploads == []
    assert doc["errors"][0]["stage"] == "resolve_store"


def test_missing_api_key_fails_before_any_store_call(tmp_path: Path) -> None:
    calls: list[str] = []
    code = run([], {}, deps(tmp_path, catalog(), calls=calls))
    assert code == 1
    assert calls == []
    assert last_run(tmp_path)["errors"][0]["stage"] == "config"


def test_publish_failure_exits_nonzero_and_records_publish_failed(tmp_path: Path) -> None:
    store = FakeStore()
    code = run([], ENV, deps(tmp_path, catalog(), store, publisher=FakePublisher(fail=True)))
    doc = last_run(tmp_path)
    assert code == 1
    assert doc["publish"] == "failed"
    assert doc["status"] == "failed"
    assert doc["errors"][-1] == {
        "article_id": None,
        "stage": "publish",
        "message": "Artifact publication failed.",
    }


def test_publish_success_sends_the_run_artifact(tmp_path: Path) -> None:
    publisher = FakePublisher()
    code = run([], ENV, deps(tmp_path, catalog(), FakeStore(), publisher=publisher))
    assert code == 0
    assert json.loads(publisher.payloads[0])["publish"] == "ok"
    assert last_run(tmp_path)["publish"] == "ok"


def test_selection_below_minimum_fails(tmp_path: Path) -> None:
    code = run(["--dry-run"], {}, deps(tmp_path, catalog()[:10]))
    assert code == 1
    assert last_run(tmp_path)["errors"][0]["stage"] == "select"


def make_doc(article_id: int, tokens: int) -> ArticleDoc:
    return ArticleDoc(article_id, 1, f"a-{article_id}", "t", "u", 1, "x", "# t\n", tokens)


@pytest.mark.parametrize("limit", [2, 3])
def test_pilot_subset_always_contains_youtube_and_longest(limit: int) -> None:
    docs = [make_doc(1, 10), make_doc(YOUTUBE_ID, 5), make_doc(3, 99), make_doc(4, 1)]
    subset = {d.article_id for d in pilot_subset(docs, limit, YOUTUBE_ID)}
    assert {YOUTUBE_ID, 3} <= subset
    assert len(subset) == limit


def test_pilot_limit_below_mandatory_files_fails_before_any_store_call(tmp_path: Path) -> None:
    calls: list[str] = []
    items = catalog({1010: "<p>" + "long text " * 300 + "</p>"})
    code = run(["--limit", "1"], ENV, deps(tmp_path, items, calls=calls))
    assert code == 1
    assert calls == []
    assert last_run(tmp_path)["errors"][0]["stage"] == "config"


class TwoCopiesStore(FakeStore):
    """Start with two completed owned copies of article 1005 at an old hash."""

    def seed_duplicates(self, article_id: int) -> list[str]:
        ids = []
        for n in (1, 2):
            fid = f"old-{n}"
            self.files[fid] = RemoteFile(
                fid,
                FileStatus.COMPLETED,
                {"managed_by": MANAGED_BY, "article_id": str(article_id), "part": 1, "sha256": "x"},
                n,
            )
            ids.append(fid)
        return ids


def test_failed_replacement_keeps_all_old_copies(tmp_path: Path) -> None:
    store = TwoCopiesStore(fail_upload={1005})
    run([], ENV, deps(tmp_path, [a for a in catalog() if a["id"] != 1005], store))
    old = store.seed_duplicates(1005)
    store.detached.clear()
    code = run([], ENV, deps(tmp_path, catalog(), store))
    assert code == 1
    assert store.detached == []
    assert set(old) <= set(store.files)


def test_successful_replacement_cleans_old_and_duplicate(tmp_path: Path) -> None:
    store = TwoCopiesStore()
    run([], ENV, deps(tmp_path, [a for a in catalog() if a["id"] != 1005], store))
    old = store.seed_duplicates(1005)
    store.detached.clear()
    assert run([], ENV, deps(tmp_path, catalog(), store)) == 0
    assert set(store.detached) == set(old)


class PollFailStore(FakeStore):
    def wait_completed(self, store_id: str, file_id: str, timeout_s: float) -> RemoteFile:
        raise UploadError("poll timeout")


def test_poll_failure_detaches_only_the_new_attachment_and_labels_poll(tmp_path: Path) -> None:
    store = PollFailStore()
    code = run([], ENV, deps(tmp_path, catalog(), store))
    doc = last_run(tmp_path)
    assert code == 1
    assert store.files == {}
    assert {e["stage"] for e in doc["errors"]} == {"poll"}


class ListFailStore(FakeStore):
    def list_files(self, store_id: str) -> list[RemoteFile]:
        from rillmark.errors import RemoteStateError

        raise RemoteStateError("page 2 failed")


def test_listing_failure_is_labeled_list_remote(tmp_path: Path) -> None:
    code = run([], ENV, deps(tmp_path, catalog(), ListFailStore()))
    assert code == 1
    assert last_run(tmp_path)["errors"][0]["stage"] == "list_remote"


@pytest.mark.parametrize("argv", [[], ["--limit", "2"]])
@pytest.mark.parametrize("required", ["1", "true", "yes", "TRUE", " Yes "])
def test_required_publish_without_gist_config_fails_before_any_gateway_call(
    tmp_path: Path, argv: list[str], required: str
) -> None:
    calls: list[str] = []
    code = run(argv, {**ENV, "REQUIRE_PUBLISH": required}, deps(tmp_path, catalog(), calls=calls))
    doc = last_run(tmp_path)
    assert code == 1
    assert calls == []
    assert doc["status"] == "failed"
    assert doc["errors"][0]["stage"] == "config"


@pytest.mark.parametrize("argv", [[], ["--limit", "2"]])
def test_required_publish_with_full_gist_config_publishes(tmp_path: Path, argv: list[str]) -> None:
    publisher = FakePublisher()
    env = {
        **ENV,
        "REQUIRE_PUBLISH": "true",
        "ARTIFACT_GIST_ID": "g",
        "ARTIFACT_GITHUB_TOKEN": "t",
    }
    code = run(argv, env, deps(tmp_path, catalog(), FakeStore(), publisher=publisher))
    assert code == 0
    assert len(publisher.payloads) == 1
    assert json.loads(publisher.payloads[0])["publish"] == "ok"
    assert last_run(tmp_path)["publish"] == "ok"


@pytest.mark.parametrize("required", ["", "0", "false", "no"])
def test_optional_publish_without_gist_config_is_skipped(tmp_path: Path, required: str) -> None:
    code = run([], {**ENV, "REQUIRE_PUBLISH": required}, deps(tmp_path, catalog(), FakeStore()))
    assert code == 0
    assert last_run(tmp_path)["publish"] == "skipped"


def test_dry_run_never_constructs_publisher_even_with_gist_config(tmp_path: Path) -> None:
    calls = []

    def factory(config):
        calls.append(config)
        raise AssertionError("publisher should not be constructed")

    d = replace(deps(tmp_path, catalog()), publisher_factory=factory)
    code = run(["--dry-run"], {"ARTIFACT_GIST_ID": "g", "ARTIFACT_GITHUB_TOKEN": "test"}, d)
    assert code == 0
    assert calls == []
    assert last_run(tmp_path)["publish"] == "skipped"


def test_dry_run_ignores_required_publish_without_gist_config(tmp_path: Path) -> None:
    calls: list[str] = []
    code = run(["--dry-run"], {"REQUIRE_PUBLISH": "true"}, deps(tmp_path, catalog(), calls=calls))
    doc = last_run(tmp_path)
    assert code == 0
    assert calls == []
    assert doc["publish"] == "skipped"
    assert doc["chunks"]["estimated"] == 32


@pytest.mark.parametrize("required", ["", "true"])
@pytest.mark.parametrize("env_extra", [{"ARTIFACT_GIST_ID": "g"}, {"ARTIFACT_GITHUB_TOKEN": "t"}])
def test_partial_gist_config_fails_before_any_store_call(
    tmp_path: Path, env_extra: dict[str, str], required: str
) -> None:
    calls: list[str] = []
    code = run(
        [],
        {**ENV, **env_extra, "REQUIRE_PUBLISH": required},
        deps(tmp_path, catalog(), calls=calls),
    )
    assert code == 1
    assert calls == []
    assert last_run(tmp_path)["errors"][0]["stage"] == "config"


def test_output_dir_io_error_still_writes_failed_artifact(tmp_path: Path) -> None:
    blocked = tmp_path / "out"
    blocked.write_text("not a directory")
    code = run(["--dry-run"], {}, deps(tmp_path, catalog()))
    doc = last_run(tmp_path)
    assert code == 1
    assert doc["status"] == "failed"
    assert doc["errors"][0]["stage"] == "convert"


def test_get_failure_preserves_nonzero_exit_and_local_failure(tmp_path: Path, caplog) -> None:
    from rillmark.report import GistPublisher

    def get(url: str, headers: dict) -> tuple[int, dict]:
        return 403, {"message": "ghp_privateTestToken"}

    def post(url: str, headers: dict, body: dict) -> tuple[int, dict]:
        raise AssertionError("PATCH must not run")

    publisher = GistPublisher("123", "ghp_privateTestToken", post, get)
    d = deps(tmp_path, catalog(), FakeStore(), publisher=publisher)
    code = run([], ENV, d)
    doc = last_run(tmp_path)
    assert code == 1
    assert doc["publish"] == "failed"
    assert doc["status"] == "failed"
    assert doc["errors"][-1]["stage"] == "publish"
    assert "ghp_privateTestToken" not in (tmp_path / "last_run.json").read_text()
    assert "ghp_privateTestToken" not in caplog.text


def test_publish_failure_logs_publish_failed_with_sync_status(tmp_path: Path, caplog) -> None:
    import logging

    caplog.set_level(logging.INFO)
    run([], ENV, deps(tmp_path, catalog(), FakeStore(), publisher=FakePublisher(fail=True)))
    events = [r.getMessage() for r in caplog.records if "publish_failed" in r.getMessage()]
    assert events and "sync_status=success" in events[0]


def test_default_publisher_reads_then_patches_gist_with_token_header(
    monkeypatch, tmp_path: Path
) -> None:
    import requests

    from rillmark.cli import _default_publisher
    from rillmark.config import load_config

    sent: dict = {}

    class Response:
        status_code = 200

        def __init__(self, body: dict) -> None:
            self.body = body

        def json(self) -> dict:
            return self.body

    def fake_get(url, headers=None, timeout=None):
        sent["get"] = (url, headers, timeout)
        return Response({"files": {}})

    def fake_patch(url, json=None, headers=None, timeout=None):
        sent.update(url=url, json=json, headers=headers, timeout=timeout)
        return Response({"html_url": "https://gist.github.com/abc"})

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "patch", fake_patch)
    env = {"ARTIFACT_GIST_ID": "abc", "ARTIFACT_GITHUB_TOKEN": "tok"}
    publisher = _default_publisher(load_config(env, SELECTION))
    assert publisher is not None
    from rillmark.models import DeltaCounts, PublishStatus, RunMode, RunResult, RunStatus
    from rillmark.report import build_last_run

    result = RunResult(
        "2026-10-31T00:00:00Z",
        RunMode.SYNC,
        RunStatus.SUCCESS,
        "2026-10-31T00:00:00Z",
        "2026-10-31T00:00:10Z",
        None,
        None,
        0,
        0,
        DeltaCounts(),
        None,
        (),
        (),
        ChunkConfig(4096, 0),
    )
    payload = json.dumps(build_last_run(result, PublishStatus.OK))
    assert publisher.publish(payload) == "https://gist.github.com/abc"
    assert sent["get"] == ("https://api.github.com/gists/abc", sent["headers"], (5, 30))
    assert sent["url"] == "https://api.github.com/gists/abc"
    assert sent["json"]["files"]["last_run.json"] == {"content": payload}
    assert (
        json.loads(sent["json"]["files"]["history.json"]["content"])["runs"][0]["run_id"]
        == result.run_id
    )
    assert sent["headers"]["Authorization"] == "Bearer tok"
    assert sent["timeout"] == (5, 30)


def test_no_publisher_without_gist_config() -> None:
    from rillmark.cli import _default_publisher
    from rillmark.config import load_config

    assert _default_publisher(load_config({}, SELECTION)) is None


class PilotPollFailStore(FakeStore):
    def wait_completed(self, store_id: str, file_id: str, timeout_s: float) -> RemoteFile:
        raise UploadError("poll timeout")


def test_pilot_poll_failure_never_detaches(tmp_path: Path) -> None:
    store = PilotPollFailStore()
    items = catalog({1010: "<p>" + "long text " * 300 + "</p>"})
    code = run(["--limit", "2"], ENV, deps(tmp_path, items, store))
    assert code == 1
    assert store.detached == []
    assert last_run(tmp_path)["mode"] == "pilot"


class CountsCrashStore(FakeStore):
    def counts(self, store_id: str) -> StoreCounts:
        raise RuntimeError("unexpected")


def test_counts_crash_keeps_null_counts_and_writes_artifact(tmp_path: Path) -> None:
    code = run([], ENV, deps(tmp_path, catalog(), CountsCrashStore()))
    doc = last_run(tmp_path)
    assert code == 0
    assert doc["store"]["files_in_store"] is None
    assert doc["files"]["actual"] is None


def test_publisher_factory_crash_fails_run_but_writes_artifact(tmp_path: Path) -> None:
    def broken_factory(config):
        raise OSError("bad publisher")

    d = replace(deps(tmp_path, catalog(), FakeStore()), publisher_factory=broken_factory)
    code = run([], ENV, d)
    doc = last_run(tmp_path)
    assert code == 1
    assert doc["publish"] == "failed"


class PollOSErrorStore(FakeStore):
    def wait_completed(self, store_id: str, file_id: str, timeout_s: float) -> RemoteFile:
        raise OSError("socket")


class DetachOSErrorStore(FakeStore):
    def detach(self, store_id: str, file_id: str) -> None:
        raise OSError("socket")


def test_unexpected_poll_error_is_labeled_poll(tmp_path: Path) -> None:
    run([], ENV, deps(tmp_path, catalog(), PollOSErrorStore()))
    assert last_run(tmp_path)["errors"][0]["stage"] == "poll"


def test_unexpected_detach_error_is_labeled_detach(tmp_path: Path) -> None:
    store = DetachOSErrorStore()
    run([], ENV, deps(tmp_path, catalog(), store))
    run([], ENV, deps(tmp_path, catalog({1005: "<p>New steps.</p>"}), store))
    assert last_run(tmp_path)["errors"][0]["stage"] == "detach"
