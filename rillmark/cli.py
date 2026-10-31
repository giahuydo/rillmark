"""Run orchestration: fetch → select → convert → sync → report → publish.

Design: docs/01-architecture.md §3 (pipeline, modes), docs/03-sync-lifecycle.md §4 (safe
replacement) and §6 (exit codes), docs/02-data-contracts.md §5 (run artifact).
Every external edge is injected through `Deps` so the whole run is testable offline.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from rillmark import report
from rillmark.config import Config, load_config
from rillmark.convert import build_docs
from rillmark.errors import ConfigError, RillmarkError, UploadError
from rillmark.models import (
    ArticleDoc,
    ChunkConfig,
    DeltaCounts,
    ErrorRecord,
    Publisher,
    PublishStatus,
    RemoteFile,
    RunMode,
    RunResult,
    RunStatus,
    Stage,
    StoreGateway,
)
from rillmark.state import classify, content_hash, file_attributes
from rillmark.zendesk import fetch_articles, http_get_json, select_articles

logger = logging.getLogger(__name__)

POLL_TIMEOUT_S = 120.0
DEFAULT_CHUNK = ChunkConfig(max_tokens=4096, overlap_tokens=0)  # used only when config failed


def serialize(doc: dict) -> str:
    """Same encoding as report.write_local: UTF-8 JSON, sorted keys, trailing newline."""
    return json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_gateway(api_key: str) -> StoreGateway:
    from rillmark.vector_store import OpenAIStoreGateway, make_client

    return OpenAIStoreGateway(make_client(api_key))


def _default_publisher(config: Config) -> Publisher | None:
    if not (config.gist_id and config.gist_token):
        return None
    import requests

    def post(url: str, headers: dict, body: dict) -> tuple[int, dict]:  # GistPublisher order
        response = requests.patch(url, json=body, headers=headers, timeout=(5, 30))
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return response.status_code, payload if isinstance(payload, dict) else {}

    return report.GistPublisher(config.gist_id, config.gist_token, post)


@dataclass(frozen=True)
class Deps:
    """Injectable edges; defaults talk to Zendesk, OpenAI, and GitHub."""

    get_json: Callable[[str], dict] = http_get_json
    gateway_factory: Callable[[str], StoreGateway] = _default_gateway
    publisher_factory: Callable[[Config], Publisher | None] = _default_publisher
    now: Callable[[], str] = _utc_now
    selection_path: Path = Path("config/selection.json")
    out_dir: Path = Path("out")
    report_path: Path = Path("last_run.json")


@dataclass
class _Progress:
    """Mutable run state collected while executing; frozen into RunResult at the end."""

    fetched: int = 0
    selected: int = 0
    docs: tuple[ArticleDoc, ...] = ()
    store_id: str | None = None
    delta: DeltaCounts = field(default_factory=DeltaCounts)
    deletion_candidates: tuple[int, ...] = ()
    errors: list[ErrorRecord] = field(default_factory=list)
    stage: Stage = Stage.CONFIG


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="main.py", description="Sync help articles once.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="fetch and convert; no OpenAI calls")
    mode.add_argument("--limit", type=int, metavar="N", help="pilot: upload at most N files")
    args = parser.parse_args(list(argv))
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer")
    return args


def pilot_subset(docs: Sequence[ArticleDoc], limit: int, youtube_id: int) -> list[ArticleDoc]:
    """Deterministic pilot set: the YouTube article, the longest file, then selection order.

    Raises ConfigError when `limit` cannot hold the mandatory files, so the cap is never exceeded.
    """
    ordered = sorted(docs, key=lambda d: d.key)
    must = [d for d in ordered if d.article_id == youtube_id]
    longest = max(ordered, key=lambda d: (d.tokens, d.key))
    if longest not in must:
        must.append(longest)
    if limit < len(must):
        raise ConfigError(f"--limit must be at least {len(must)} (YouTube article + longest file)")
    rest = [d for d in ordered if d not in must]
    return (must + rest)[:limit]


def _write_markdown(docs: Sequence[ArticleDoc], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        (out_dir / doc.filename).write_text(doc.markdown, encoding="utf-8")


def _record_failure(progress: _Progress, stage: Stage, article_id: int | None) -> None:
    progress.errors.append(ErrorRecord(stage, stage.value, article_id))
    progress.delta = replace(progress.delta, failed=progress.delta.failed + 1)
    logger.warning("action=failed article_id=%s stage=%s", article_id, stage.value)


def _upload(
    gateway: StoreGateway,
    store_id: str,
    doc: ArticleDoc,
    config: Config,
    progress: _Progress,
    *,
    cleanup: bool,
) -> RemoteFile | None:
    """Upload and wait for completion; on failure record it and return None.

    With `cleanup`, a new attachment that never completes is detached (it is ours by file ID);
    pilot runs pass cleanup=False and never detach. The previous completed attachment is never
    touched here (docs/03 §4).
    """
    sha = content_hash(doc.markdown, config.chunk)
    progress.stage = Stage.UPLOAD
    try:
        attached = gateway.upload(store_id, doc, file_attributes(doc, sha), config.chunk)
    except UploadError:
        _record_failure(progress, Stage.UPLOAD, doc.article_id)
        return None
    progress.stage = Stage.POLL
    try:
        return gateway.wait_completed(store_id, attached.file_id, POLL_TIMEOUT_S)
    except UploadError:
        _record_failure(progress, Stage.POLL, doc.article_id)
        if cleanup:
            progress.stage = Stage.DETACH
            try:
                gateway.detach(store_id, attached.file_id)
            except RillmarkError:
                logger.warning("cleanup_failed article_id=%s stage=detach", doc.article_id)
        return None


def _detach(gateway: StoreGateway, store_id: str, old: RemoteFile, progress: _Progress) -> None:
    progress.stage = Stage.DETACH
    try:
        gateway.detach(store_id, old.file_id)
    except RillmarkError:
        article_id = old.attributes.get("article_id")
        _record_failure(progress, Stage.DETACH, int(article_id) if article_id else None)
        return
    progress.delta = replace(progress.delta, deleted=progress.delta.deleted + 1)


def _sync(
    gateway: StoreGateway,
    config: Config,
    docs: Sequence[ArticleDoc],
    allowed: set[str] | None,
    progress: _Progress,
) -> None:
    """Resolve the store, classify, and apply the delta (docs/03 §3-§5).

    `allowed` is the pilot key set (None for a full sync). Pilot runs never detach.
    """
    progress.stage = Stage.RESOLVE_STORE
    store_id = gateway.resolve_store(config.vector_store_id)
    progress.store_id = store_id
    progress.stage = Stage.LIST_REMOTE
    remote = gateway.list_files(store_id)
    plan = classify(docs, remote, config.chunk)
    progress.deletion_candidates = plan.deletion_candidates
    progress.stage = Stage.UPLOAD
    pilot = allowed is not None

    def wanted(doc: ArticleDoc) -> bool:
        return allowed is None or doc.key in allowed

    # Keys whose desired content is confirmed completed in the store; only these may be deduped.
    confirmed = {d.key for d in plan.skipped}
    progress.delta = replace(progress.delta, skipped=len([d for d in plan.skipped if wanted(d)]))
    for doc in (d for d in plan.added if wanted(d)):
        if _upload(gateway, store_id, doc, config, progress, cleanup=not pilot):
            progress.delta = replace(progress.delta, added=progress.delta.added + 1)
            logger.info("action=added article_id=%s", doc.article_id)
    replacements = [(r, "updated") for r in plan.updated] + [(r, "added") for r in plan.retried]
    for repl, kind in replacements:
        if not wanted(repl.new):
            continue
        if not _upload(gateway, store_id, repl.new, config, progress, cleanup=not pilot):
            continue  # old attachment kept; retried next run
        confirmed.add(repl.new.key)
        progress.delta = replace(progress.delta, **{kind: getattr(progress.delta, kind) + 1})
        logger.info("action=%s article_id=%s", kind, repl.new.article_id)
        if not pilot:
            _detach(gateway, store_id, repl.old, progress)
    if not pilot:
        for duplicate in plan.duplicates:
            if duplicate.key in confirmed:
                _detach(gateway, store_id, duplicate, progress)


def _status(progress: _Progress, fatal: bool) -> RunStatus:
    if fatal:
        return RunStatus.FAILED
    return RunStatus.PARTIAL_FAILURE if progress.errors else RunStatus.SUCCESS


def _check_publisher_config(config: Config, *, required: bool) -> None:
    if bool(config.gist_id) != bool(config.gist_token):
        raise ConfigError("ARTIFACT_GIST_ID and ARTIFACT_GITHUB_TOKEN must be set together")
    if required and not config.gist_id:
        raise ConfigError(
            "ARTIFACT_GIST_ID and ARTIFACT_GITHUB_TOKEN are required when REQUIRE_PUBLISH is set"
        )


def run(argv: Sequence[str], env: Mapping[str, str], deps: Deps | None = None) -> int:
    """Execute one run and return the process exit code (docs/03 §6)."""
    deps = deps or Deps()
    args = parse_args(argv)
    mode = RunMode.DRY_RUN if args.dry_run else RunMode.PILOT if args.limit else RunMode.SYNC
    started = deps.now()
    progress = _Progress()
    fatal = False
    config: Config | None = None
    gateway: StoreGateway | None = None
    try:
        config = load_config(env, deps.selection_path)
        if mode is not RunMode.DRY_RUN:
            _check_publisher_config(
                config,
                required=env.get("REQUIRE_PUBLISH", "").strip().lower() in {"1", "true", "yes"},
            )
            if not config.api_key:
                raise ConfigError("API_KEY (or OPENAI_API_KEY) is required outside --dry-run")
        progress.stage = Stage.FETCH
        articles = fetch_articles(deps.get_json, config.zendesk_base_url)
        progress.fetched = len(articles)
        progress.stage = Stage.SELECT
        selected = select_articles(articles, config.selection)
        progress.selected = len(selected)
        progress.stage = Stage.CONVERT
        docs = tuple(build_docs(selected, config.chunk.max_tokens))
        progress.docs = docs
        _write_markdown(progress.docs, deps.out_dir)
        if mode is not RunMode.DRY_RUN:
            allowed = None
            if args.limit is not None:
                progress.stage = Stage.CONFIG
                progress.docs = tuple(
                    pilot_subset(docs, args.limit, config.selection.youtube_article_id)
                )
                allowed = {d.key for d in progress.docs}
            progress.stage = Stage.RESOLVE_STORE
            gateway = deps.gateway_factory(config.api_key or "")
            _sync(gateway, config, docs, allowed, progress)
    except (RillmarkError, OSError) as exc:
        fatal = True
        progress.errors.append(ErrorRecord(progress.stage, progress.stage.value))
        logger.error("run failed stage=%s error=%s", progress.stage.value, type(exc).__name__)
    except Exception as exc:  # last-resort boundary: record a generic failure, never the message
        fatal = True
        progress.errors.append(ErrorRecord(progress.stage, progress.stage.value))
        logger.error("run failed stage=%s error=%s", progress.stage.value, type(exc).__name__)

    store_counts = None
    if gateway is not None and progress.store_id is not None:
        try:
            store_counts = gateway.counts(progress.store_id)
        except Exception:  # observation only: unknown counts stay null, never fabricated zeros
            logger.warning("store_counts_unavailable run_id=%s", started)
    result = RunResult(
        run_id=started,
        mode=mode,
        status=_status(progress, fatal),
        started_at=started,
        finished_at=deps.now(),
        git_sha=env.get("RENDER_GIT_COMMIT") or env.get("GIT_SHA"),
        vector_store_id=progress.store_id,
        fetched=progress.fetched,
        selected=progress.selected,
        delta=progress.delta,
        store=store_counts,
        deletion_candidates=progress.deletion_candidates,
        docs=progress.docs,
        chunk_config=config.chunk if config else DEFAULT_CHUNK,
        errors=tuple(progress.errors),
    )
    return _finish(result, config, mode, deps)


def _finish(result: RunResult, config: Config | None, mode: RunMode, deps: Deps) -> int:
    """Publish (when configured), write the local artifact, log the summary, map the exit."""
    # Failed runs still publish their safe metadata, so the public link shows the failure.
    publish = PublishStatus.SKIPPED
    try:
        publisher = (
            deps.publisher_factory(config) if config and mode is not RunMode.DRY_RUN else None
        )
        if publisher is not None:
            payload = report.build_last_run(result, PublishStatus.OK)
            publish = report.publish_artifact(publisher, serialize(payload))
    except Exception:  # publisher construction/transport bugs must not lose the local artifact
        publish = PublishStatus.FAILED
    if publish is PublishStatus.FAILED:
        logger.error(
            "publish_failed run_id=%s reason=publisher_error sync_status=%s",
            result.run_id,
            result.status.value,
        )
        result = replace(
            result,
            status=RunStatus.FAILED,
            errors=(*result.errors, ErrorRecord(Stage.PUBLISH, "publish_failed")),
        )
    doc = report.build_last_run(result, publish)
    try:
        report.write_local(deps.report_path, doc)
    except OSError:
        print(f"write_local_failed run_id={result.run_id}", file=sys.stderr)
        return 1
    logger.info(report.summary_line(doc))
    return 0 if result.status is RunStatus.SUCCESS and publish is not PublishStatus.FAILED else 1
