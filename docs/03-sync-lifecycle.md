# 03 — Sync Lifecycle

Back to [docs index](README.md). Related: [ADR-0003](adr/0003-sync-state.md), [02-data-contracts](02-data-contracts.md#4-vector-store-file-attributes), [04-operations](04-operations.md).

## 1. Requirements

R12–R13: re-scrape, detect new and updated articles, upload only the delta, and log added/updated/skipped. Constraints: the filesystem is ephemeral (Render Cron), there is no database, and a marked store is resolved in the key's project ([ADR-0001](adr/0001-ai-provider.md#5-consequences)).

## 2. State model

- **Desired state**: complete Zendesk sweep with versioned `config/selection.json`: `section_ids` = `[26324076807315, 26324141467539, 26324224269459]`, `youtube_article_id` = `360051014713`, `min_articles` = 30. Env `SECTION_IDS` / `YOUTUBE_ARTICLE_ID` are optional overrides. Canonical key `article_id/part` (unsplit = part 1); count distinct articles separately from file keys. Pilot `--limit N` caps uploads only after full ≥30 selection validation; deterministic subset includes YouTube and the longest file, and never detaches/deletes.
- **Store identity**: `VECTOR_STORE_ID` set → retrieve it, require vector store `metadata.managed_by = "rillmark-optibot-v1"`, else fail closed. Unset → list stores in the key's project (all pages), filter by that marker: 0 → create named `rillmark-optibot` with marker and no `expires_after`; 1 → reuse; >1 → fail closed. Display name never matches identity. `--init-store` is removed.
- **Remote state**: `vector_stores.files.list(resolved store)` (all pages), giving `{file_id, status, attributes}`. Only attachments with file-attribute marker `managed_by = "rillmark-optibot-v1"` in that store are owned. Legacy/foreign/manual entries are not automatically detached.
- **Hash input** = `sha256("v{schema_version}\nchunk={max}/{overlap}\n" + normalized_markdown)` per [02 §3](02-data-contracts.md#3-html--markdown-normalization-rules), so schema or chunk-setting changes re-upload.

ASSUMPTION (check in P2): the list call returns `attributes` per file. Fallback: `vector_stores.files.retrieve` per file (about 30–60 calls, acceptable).

## 3. Delta classification (pure function)

| Desired | Remote (status `completed`) | Class | Action |
|---|---|---|---|
| present | absent | **added** | upload + attach |
| present | present, same sha | **skipped** | none |
| present | present, different sha | **updated** | safe replace (§4) |
| absent | completed owned attachment | **deletion candidate** | log `deletion_candidates` count + article IDs only; never detach/delete for source absence |
| present | owned entry with `failed`/`cancelled` only | **added** (retry) | upload + attach + poll; detach failed entry only after replacement completes |

`Last-Modified` / `updated_at` is logged but not trusted for skipping. Zendesk bumps it for metadata edits, and the hash is cheaper than being wrong. Fetching every article each day costs one paginated API sweep (a few requests).

**Source-absence deletion deferred (8 h budget).** After complete source and remote pagination, log absent owned article IDs/count as `deletion_candidates` only; never detach/delete for source absence, including in pilot. Failed or incomplete listing is an error, not evidence of zero candidates. No approved-scope baseline, deletion-spike guard, or automatic source-absence cleanup path is built. The only automatic detach is same-key update replacement (§4).

## 4. Safe update order

```
for each updated article:
  1. upload new file           (files.create)
  2. attach with attributes     (vector_stores.files.create)
  3. poll until status=completed (timeout, e.g. 120 s)
  4. only then: detach the same `article_id/part` old owned attachment from the resolved marked store
on failure at 1–3: keep the old attachment; detach any newly attached failed/incomplete replacement only after checking its ownership and ID; count failed++ and retry safely next run
```

Attach-before-detach preserves the old completed attachment if upload/attach/poll fails. Check the replacement is completed before detaching the old; if detach fails, keep both and retry dedup next run. The temporary two-version retrieval window is not proof of identical answers; log/reconcile duplicates. OpenAI's [OpenAPI specification](https://raw.githubusercontent.com/openai/openai-openapi/master/openapi.yaml) documents `DELETE /vector_stores/{vector_store_id}/files/{file_id}` as removing an attachment **without deleting the File object**, whereas `DELETE /files/{file_id}` removes it from **all** vector stores (read-only check at planning time). Therefore sync uses store-scoped detach only for same-key replacement cleanup; source-absence detach and global Files API deletion are disabled. A failed upload may leave an orphan File object for audited manual cleanup; never remove a shared/foreign file globally.

## 5. Recovery and dedup

A crash between steps 3 and 4 leaves **two completed owned attachments with the same canonical `article_id/part` (unsplit = part 1)**. At the start of every sync run, `load_remote_state` groups owned attachments by that key:

- With duplicates, keep a completed attachment matching the desired hash; when none match, upload the desired version first and keep the old until completion. Detach only confirmed owned duplicates in the resolved marked store after the replacement is completed; failed detach remains visible and retried, not counted as success. Unexpected duplicates or inconsistent attributes block destructive action for that key pending review. Pilot never performs destructive dedup.
- Files with missing/unknown `managed_by` (even if `article_id` is present), or foreign/manual uploads: log a warning and do **not** detach them. They count toward `files_in_store`, but not managed counts.

With complete fetch/list and successful operations, a rerun of desired keys gives `added=0, updated=0, skipped=desired managed file-key count`; source-absent candidates remain, so this does not claim full-store convergence or imply `skipped=article count` if splitting is enabled.

## 6. Exit codes

| Outcome | Exit | `status` / publish |
|---|---|---|
| Sync **and** required publish succeed (including “nothing to do”) | 0 | `success`, `publish=ok` |
| Sync partial/failed (including config, Zendesk, remote-list or auth failure) | 1 | `partial_failure` or `failed`; `publish=ok|failed|skipped` as observed |
| Sync ok but required publish failed | 1 | `failed`, `publish=failed`, error `publish_failed` |

`--dry-run` = no OpenAI calls (still fetches Zendesk). Pilot counts are labeled `pilot`. Write local `last_run.json` even on failure (best effort); a public URL may be stale after failed publication and must never claim to show the latest attempt. `files.actual` is observed `file_counts.completed`; `chunks.estimated` + `chunks.basis` are estimates and `chunks.actual = null` (G3 UNKNOWN).

## 7. Tradeoffs

- **Hash vs `updated_at`**: the hash catches real changes only, with no false skips. The cost is a full re-fetch each run, which is trivial at this scale.
- **Attributes vs a separate manifest file**: attributes are atomic with the file. A manifest could drift from the store. See [ADR-0003](adr/0003-sync-state.md).
- **Source absence**: cleanup deferred for the 8 h budget; log `deletion_candidates` instead. Stale files can remain until a separately approved deletion design; replacement cleanup remains store-scoped and ownership-checked.

## 8. Acceptance gates

- [ ] Unit tests for every row in the §3 table, incomplete fetch/list failures and candidate logging without detaches, and ownership-aware duplicate/retry cases ([05](05-testing.md#2-test-matrix)).
- [ ] Live check: run 1 gives `added=N` for desired file keys. Run 2 gives `skipped=N, added=0, updated=0` for those keys. After editing one local fixture (or changing max/overlap), `updated` > 0.
- [ ] Kill-test (optional): interrupt between attach and old-version detach; the next sync converges to exactly one completed owned attachment per desired `article_id/part` (not necessarily one file per article if splitting is enabled). Source-absent candidates stay logged and retained.
