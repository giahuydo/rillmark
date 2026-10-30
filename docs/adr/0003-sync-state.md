# ADR-0003 — Sync State in Vector-Store File Attributes

Back to [docs index](../README.md). Related: [03-sync-lifecycle](../03-sync-lifecycle.md), [02 §4](../02-data-contracts.md#4-vector-store-file-attributes).

- **Status:** Accepted. One assumption is checked in P2 (does `list` return attributes?).

## 1. Context

The daily job must upload only the delta (R12) and log added/updated/skipped (R13). The Render Cron filesystem is ephemeral, and there is no database by design. Reruns and crashes must converge to the right state.

## 2. Decision

- **Change signal:** `sha256("v{schema_version}\nchunk={max}/{overlap}\n" + normalized_markdown)`. Changes to max chunk size/overlap re-upload. `updated_at` / `Last-Modified` are logged but **not** used to skip, because Zendesk bumps them on metadata-only edits.
- **Store identity:** vector store `metadata.managed_by = "rillmark-optibot-v1"`; if `VECTOR_STORE_ID` is set, retrieve and require that marker, else fail closed. If unset, list all pages in the key's project and filter on marker: 0 → create named `rillmark-optibot` with marker and no `expires_after`; 1 → reuse; >1 → fail closed. Display name is never used for matching. `--init-store` is removed.
- **Source of truth for "what is uploaded":** the resolved marked store itself. Each owned attachment carries file-attribute marker `managed_by = "rillmark-optibot-v1"` plus `article_id`, `sha256`, `url`, `slug`, `part`, `section_id`, `source_updated_at`, and `schema_version` (9 of 16 allowed keys). Canonical key is `article_id/part`, unsplit = part 1. `article_id` alone does not prove ownership; legacy/manual entries are not automatically detached.
- **Each sync run:** paginate source and resolved store, classify (pure function), apply attach-before-detach only for own update replacements, dedupe owned attachments on startup ([03 §3–§5](../03-sync-lifecycle.md#3-delta-classification-pure-function)). Source-absent IDs are only logged as `deletion_candidates`. Pilot `--limit N` validates the full ≥30 selection first, includes YouTube and longest file, and never detaches/deletes.

## 3. Alternatives considered

| Option | Why rejected |
|---|---|
| SQLite or Postgres state | Extra infrastructure. Cron storage is ephemeral, so a hosted DB would be needed. Overkill for about 60 rows. |
| Manifest JSON stored as a file, gist, or in the store | Can drift from the real store after a partial failure. Attributes are written atomically with the file. |
| `updated_at` comparison only | Gives false "updated" results on metadata bumps, and misses converter changes. |
| Delete-all then re-upload every run | Not a delta (fails R12), and the store is empty or partial during the run. |

## 4. Consequences

- **Idempotent:** a second run with unchanged approved scope/source and successful processing gives `added=0, updated=0, skipped=N` where N is the managed part-file count, not necessarily the article count.
- **Crash-safe:** on retry keep the old completed attachment until its replacement is completed; detach only owned duplicates in this store. If detach fails, retain both and retry. An inconsistent/missing ownership marker blocks destructive cleanup.
- **Source-absence deletion deferred (8 h budget):** absent owned articles are logged as `deletion_candidates` count + IDs only; no source-absence detach/delete, no selection baseline or spike guard. Failed source/list pagination is an error, not proof of absence. Replacement cleanup of an article's own old version remains allowed after new completion, store-scoped and ownership-checked ([03 §3](../03-sync-lifecycle.md#3-delta-classification-pure-function)).
- **Store-scoped detach only:** OpenAI [OpenAPI spec](https://raw.githubusercontent.com/openai/openai-openapi/master/openapi.yaml) describes `DELETE /vector_stores/{vector_store_id}/files/{file_id}` as removing the attachment but not the underlying File; `DELETE /files/{file_id}` removes it from all vector stores. Sync never calls the global delete endpoint. Exclusive ownership/other consumers of any orphan File object remain UNKNOWN; manual audited cleanup only until verified.
- **ASSUMPTION (P2):** `vector_stores.files.list` returns `attributes`. Fallback: one `retrieve` call per file (about 30–60 calls).
