# 02 — Data Contracts

Back to [docs index](README.md). Related: [01-architecture](01-architecture.md), [03-sync-lifecycle](03-sync-lifecycle.md), [ADR-0002](adr/0002-chunking-and-citation.md).

## 1. Zendesk input

**Endpoints** (public Help Center API; A1/A2 resolved by the VERIFIED 2026-10-30 discovery snapshot: anonymous HTTP 200, 13 categories, 74 sections, 416 `en-us` non-draft articles; future availability remains unguaranteed):

| Purpose | Endpoint |
|---|---|
| Articles | `GET https://support.optisigns.com/api/v2/help_center/en-us/articles.json?per_page=100` (follow `next_page`) |
| Sections | `GET https://support.optisigns.com/api/v2/help_center/en-us/sections.json` |
| Categories | `GET https://support.optisigns.com/api/v2/help_center/en-us/categories.json` |

**Fields consumed** (anything else is ignored):

| Field | Use |
|---|---|
| `id` | Primary key (`article_id`) |
| `title` | H1 and slug source |
| `body` | HTML, converted to Markdown |
| `html_url` | **Canonical citation URL** (`Article URL:`) |
| `section_id` | Selection and metadata |
| `locale` | Must be `en-us` |
| `draft` | Skip if `true` |
| `updated_at` | Metadata only; **not** used for change detection (see [ADR-0003](adr/0003-sync-state.md)) |

**Selection rule.** Versioned non-secret `config/selection.json`: `section_ids` = `[26324076807315, 26324141467539, 26324224269459]`, `youtube_article_id` = `360051014713`, `min_articles` = 30. Env `SECTION_IDS` / `YOUTUBE_ARTICLE_ID` are optional overrides. Apply `en-us`, non-draft and section filters; fail if fewer than 30 selected or the YouTube article is missing. No implicit recent-article fallback. The VERIFIED discovery snapshot from 2026-10-30 is summarized below (counts may change):

| Section ID | Name | Articles |
|---|---|---:|
| `26324076807315` | Youtube & Other Video Platforms | 9 |
| `26324141467539` | Social Media | 16 |
| `26324224269459` | News & RSS | 12 |
| **Total** | | **37** |

The required article is `360051014713`, [How to Use YouTube with OptiSigns](https://support.optisigns.com/hc/en-us/articles/360051014713-How-to-Use-YouTube-with-OptiSigns). `--limit N` caps uploads only **after** the full ≥30 validation: choose a deterministic subset including this article and the longest file, label counts `pilot`, and never detach/delete in pilot. Source absence in normal sync produces `deletion_candidates`, not detach.

## 2. Markdown file contract

**Filename:** `<slug>.md`. `slug` = lower-kebab of the title (ASCII, ≤ 80 chars). On collision, append `-<article_id>`. Within one store, the filename is unique per article. It is what the Playground citation chip shows ([ADR-0002](adr/0002-chunking-and-citation.md#3-citation-path-filename--zendesk-url)).

**Content layout:**

```markdown
# {title}

Article URL: {html_url}

{body as Markdown}
```

- The `Article URL:` line uses the **exact token from the system prompt**. The model copies it from retrieved text into its answer.
- No volatile values in the file (no `updated_at`, no fetch timestamp), so the hash changes only when the content does.
- Default: one file per article. Validate the serialized Markdown token budget **including the header**; oversize files fail the run clearly, never silently truncate. Only if P1 measurement requires H2 splitting ([ADR-0002](adr/0002-chunking-and-citation.md#2-decision)), each part is `<slug>--p<n>.md` with the repeated H1 and `Article URL:` header. `selected` counts distinct articles; completed managed attachments count file attachments, which can exceed `selected`; neither is an actual embedded chunk count.

## 3. HTML → Markdown normalization rules

| Element | Rule | Rubric reason |
|---|---|---|
| Headings `h1–h6` | Title is the only H1; demote body `<h1>` to `##` (fixture `52412502456083`); preserve other ATX heading levels. | “preserve headings” |
| `pre`/`code` | Fenced code blocks; language kept when a `class="language-x"` is present; inline `code` kept | “preserve code blocks” |
| Links `<a href>` | Keep text and **href verbatim**, including fragments, relative paths, `mailto:` and `tel:` (fixture `33382537925267`). Drop `<a name>` / empty-href anchor element, retaining any text (fixture `8899727608083`); broken in-page `#fragment` jumps are an accepted caveat. | “preserve relative links” |
| Images | Keep `![alt](src)` verbatim; missing `alt` → filename stem. Relative image `src` (e.g. `/attachments/…`, fixture `360024310813`) stays verbatim per R3, but may not render outside Zendesk. | content fidelity |
| YouTube `<iframe>` | For `www.youtube.com`, `www.youtube-nocookie.com`, including protocol-relative `//…/embed/<id>`, link to canonical `https://www.youtube.com/watch?v=<id>`; missing title → `embedded video` (fixtures `33382537925267`, `8899727608083`). | YouTube answer quality |
| Other `<iframe>` | Canva/Wistia/other: `[Embedded content](<src>)` link; never silently drop (fixtures `29217646663187`, `23566927217939`). Vimeo not observed; handle as other unless separately validated. | content fidelity |
| Tables | GFM tables, plain text rows for merged cells (fixtures `48241081473043`, `1500001985341`). Single-cell NOTE tables → `> **Note:**` quote (fixture `8899727608083`). | fidelity |
| `<figure>`, `<figcaption>` | Unwrap and retain image/table plus caption text (fixtures `33382537925267`, `55719322614803`). | content fidelity |
| `<blockquote>` | Markdown quote (fixture `52412502456083`). | content fidelity |
| `script`, `style`, `nav`, tracking pixels, wrappers | Remove scripts/styles/nav/tracking pixels and **empty** `div`/`span`; unwrap non-empty decorated `div`/`span` and retain content (fixtures `1500001985341`, `8899727608083`). | “remove nav/ads” without losing content |
| Whitespace | Collapse 3+ blank lines to 1; strip trailing spaces; `\n` line endings; final newline. Outside code only: NBSP → space, remove zero-width characters (fixtures `8899727608083`, `360024310813`). Preserve code whitespace. | stable hash |
| Unicode | NFC normalization outside code only; code content stays verbatim. | stable hash |

G6: The VERIFIED 416-body HTML survey and the ten fixture IDs above cover observed patterns; `<details>`/accordions, Vimeo, scripts/styles/nav and tracking-pixel removal remain untested in the snapshot (use synthetic cases for their rules). This is not a claim that every future body pattern is known.

Tradeoff: we do not convert relative links to absolute ones. The assignment says *preserve*, and the citation URL comes from the header, not from body links. Open question: a reviewer might prefer absolute URLs. Decision: keep them verbatim. One sentence in the README explains why.

## 4. Vector-store file attributes

Store identity: vector store `metadata.managed_by = "rillmark-optibot-v1"` (retrieve/set on create; match this marker, not display name). Independently, each owned attachment has file-attribute marker `managed_by = "rillmark-optibot-v1"`, attached on `vector_stores.files.create(..., attributes=…)`. Limits: ≤ 16 keys (DOCUMENTED); value lengths to confirm in P2.

| Key | Type | Example | Use |
|---|---|---|---|
| `managed_by` | string | `"rillmark-optibot-v1"` | File-attribute ownership marker; only these attachments in the resolved marked store are eligible for replacement cleanup (legacy files need manual review) |
| `article_id` | string | `"360012345678"` | Join key for the sync |
| `sha256` | string (64 hex) | `"9f2c…"` | Change detection |
| `url` | string | `html_url` | Citation verification map |
| `slug` | string | `"add-a-youtube-video"` | Debugging |
| `part` | number | `1` | Always present: unsplit article = part 1; split parts start at 1 |
| `section_id` | string | | Selection audit |
| `source_updated_at` | string (ISO-8601) | | Informational |
| `schema_version` | number | `1` | Forces re-upload when the format changes |

## 5. `last_run.json` (public artifact)

```json
{
  "run_id": "2026-11-02T03:00:04Z",
  "status": "success | partial_failure | failed",
  "mode": "sync | pilot | dry-run",
  "publish": "ok | failed | skipped",
  "started_at": "…", "finished_at": "…",
  "git_sha": "…",
  "vector_store_id": "vs_…",
  "counts": { "fetched": 0, "selected": 0, "added": 0, "updated": 0,
              "skipped": 0, "deleted": 0, "failed": 0 },
  "store": { "files_in_store": 0, "files_completed": 0, "managed_files_completed": 0 },
  "files": { "actual": 0, "basis": "file_counts.completed" },
  "deletion_candidates": { "count": 0, "article_ids": [] },
  "chunks": { "estimated": 0, "basis": "single-chunk-invariant | tiktoken-estimate",
              "max_chunk_size_tokens": 0, "largest_file_tokens": 0, "actual": null },
  "errors": [ { "article_id": "…", "stage": "upload", "message": "…" } ]
}
```

`counts.fetched` and `counts.selected` are distinct Zendesk article counts. Delta counts (`added`, `updated`, `skipped`, `deleted`, `failed`) count file-attachment operations by canonical `article_id/part` (unsplit = part 1), **not** articles or embedded chunks. `deleted` is only successful store-scoped replacement detaches; source absence never increments it. `deletion_candidates` logs absent managed article IDs/count only; no source-absence detach/delete, including in pilot. `store.files_in_store` counts all attachments (including foreign files), `store.files_completed` all completed attachments; `files.actual` is the actual provider `file_counts.completed` and `store.managed_files_completed` counts completed managed file attachments. Neither is an embedded chunk count. If remote observation fails, these counts are `null`, never fabricated zero; in dry-run remote counts are `null`. Pilot counts must be labeled `mode=pilot` and cannot be presented as full convergence. `chunks.estimated` is a tokenizer/config estimate with `chunks.basis`; `chunks.actual = null`. G3 stays **UNKNOWN**: retrieval verifies citations, not chunk cardinality ([ADR-0002](adr/0002-chunking-and-citation.md#4-chunk-count-logging-gate-g3)). `publish=failed` yields exit 1 and `publish_failed`; a public URL may remain stale and never claims to be the latest attempt. The artifact holds no secrets.

## 6. Acceptance gates

- [ ] Fixture tests cover every row in §3 ([05](05-testing.md#2-test-matrix)).
- [ ] Converting the same HTML twice gives byte-identical Markdown (hash stable).
- [ ] Every `.md` has an H1 and exactly one `Article URL:` line (per part), equal to `html_url`.
- [ ] `last_run.json` validates against §5: `selected=1` with two parts means two completed managed file attachments, not two articles; `chunks.actual=null`, `files.actual=file_counts.completed` when observed. Source-absence candidates remain visible without deletion; publish failures report `publish_failed`/exit 1.
