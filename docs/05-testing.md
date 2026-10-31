# 05 — Testing & Acceptance Evidence

Back to [docs index](README.md). Related: [00-requirements](00-requirements.md), [phases](phases.md).

## 1. Strategy

- **Unit (pytest, no network, no keys)** on the pure core: convert, slug, hash, classify, chunk estimate, report schema. This is the +5 bonus and also protects the 25-pt scrape-quality area.
- **Fake client** for `vector_store.py`: an in-memory store that implements upload/attach/list/store-scoped detach and failed operations, used to test update *ordering*, ownership and recovery. Global Files API delete is not a sync action. No network mocks.
- **Live checks** (manual, cost-gated by G0) for anything only the provider can prove.

## 2. Test matrix

| Area | Case | Type | Req |
|---|---|---|---|
| Convert | Title only H1; body H1 → H2 (`52412502456083`); other headings, fenced/inline code and language (`55719322614803`) | unit, raw fixture | R3 |
| Convert | Relative link/fragment preserved (`33382537925267`); `<a name>`/empty href removed but text kept (`8899727608083`); mailto/tel retained; synthetic `/hc/…` | unit | R3 |
| Convert | YouTube/no-cookie/protocol-relative iframe → canonical watch URL, missing title → `embedded video` (`33382537925267`, `8899727608083`) | unit, raw fixture | R3, R8 |
| Convert | Canva/Wistia/other iframe → `[Embedded content](<src>)` (`29217646663187`, `23566927217939`); no silent drop; synthetic Vimeo | unit | R3 |
| Convert | Figure unwrap image/table and caption (`33382537925267`, `55719322614803`); nonempty decorated wrappers preserved (`1500001985341`); blockquote (`52412502456083`); NOTE table (`8899727608083`) | unit, raw fixture | R3 |
| Convert | Merged-cell table fallback (`48241081473043`, `1500001985341`); missing image alt → filename stem; relative `/attachments/…` kept verbatim (`360024310813`) | unit | R3 |
| Convert | NBSP → space, zero-width removed **outside code** (`8899727608083`, `360024310813`); preserve code whitespace, normalize LF/NFC; `360042424294` small-body regression; synthetic script/style/nav/tracking removal | unit | R3 |
| Convert | H1 plus exactly one `Article URL:` per file, equal to `html_url`; repeated conversion byte-identical | unit | R2, R8, R12 |
| Slug | Collision → `-<article_id>`; ASCII; ≤80 chars | unit | R2 |
| Store | `VECTOR_STORE_ID` retrieve + marker required; ID without marker fails closed; unset list all pages with 0 marked → create with metadata/no expiry, 1 → reuse, >1 → fail closed; display name ignored | fake client | R4 |
| CLI config | Versioned `config/selection.json` values, optional env overrides; `--dry-run` still fetches Zendesk but no OpenAI calls; default sync requires key, optional ID; no `--init-store` | unit | R1, R4 |
| Select/pilot | Full selection <30 or YouTube missing fails **before** `--limit N`; deterministic subset includes YouTube + longest serialized file; cap counts `pilot`; no detach/delete even for duplicates or source absence | unit/fake client | R1, R12 |
| Classify | Added/skipped/updated/failed retry, absent owned entries logged as `deletion_candidates` with count + IDs, never detached; incomplete source/list fails | unit | R12 |
| Classify | Duplicate owned completed attachments keep desired hash; missing/foreign `managed_by` or inconsistent attrs never detached | unit | R12 |
| Sync order | New attachment completes **before** store-scoped detach of same `article_id/part` old version; failure keeps old; retry converges; no global `files.delete` | fake client | R12 |
| Hash/budget | `sha256("v{schema_version}\nchunk={max}/{overlap}\n" + normalized_markdown)` changes when max/overlap changes; serialized header included in token budget, oversize fails clearly; split only if P1 needs it | unit | R12 |
| Chunks/report | `files.actual=file_counts.completed` observed; `chunks.estimated` with `chunks.basis`, `chunks.actual=null`; `selected` article count distinct from completed managed attachments; G3 stays UNKNOWN | unit | R6 |
| Report/exits | `mode=sync|pilot|dry-run`, `deletion_candidates`, `publish=ok|failed|skipped`; sync partial/failed → 1, sync ok + publish fail → 1 and `publish_failed`; stale public URL not latest-attempt claim | unit | R13 |
| Docker | Default sync with project key and optional `VECTOR_STORE_ID` resolves/creates marked store → 0 only after required publish; dry-run no OpenAI env | live/offline | R10 |
| Delta live | Run twice → second run all desired keys skipped; observed managed attachments reconcile with file report, `file_counts.completed` includes foreign files | live | R4, R6, R12 |

All **ten** surveyed fixtures are referenced by ID in this matrix; future unobserved HTML behaviors use synthetic inputs. Source-absence deletion guards are intentionally not tested because source-absence deletion is deferred.

## 3. Acceptance evidence

| ID | Evidence | Captured how | Status today |
|---|---|---|---|
| E1 | ≥ 30 `.md` files plus a sample file in the repo (`samples/`) | `--dry-run` | Not started |
| E2 | Run log: selected articles, completed managed uploaded part-files, all-store `file_counts`, estimated chunk line with method/uncertainty; actual remains `null`; G3 UNKNOWN | live run | Not started; needs G0 |
| E3 | **G1**: Playground → File search → *Attach existing vector store* finds the API-created store by name or ID | [Screenshot](screenshots/openai/optibot-youtube-playground.png) | **PARTIAL (2026-10-31):** File search ran and cited an uploaded Markdown file; the screenshot does not display the attached store ID, so API-created store identity is not independently proven in the image. |
| E4 | **G2**: verbatim prompt; first-turn question “How do I add a YouTube video?”; answer has ≤ 5 bullets and an `Article URL: https://support.optisigns.com/hc/en-us/articles/…` line for the **right** article, plus the file citation chip | [Screenshot](screenshots/openai/optibot-youtube-playground.png) (also embedded in root README) | **PARTIAL (2026-10-31):** correct first-turn YouTube answer and file citation are visible, but no explicit `Article URL:` line appears in that answer; this acceptance gate remains open. |
| E5 | **G3**: pilot file IDs/status/chunk settings + beginning/middle/end search results (retrieval evidence only), document whether authoritative per-file chunk enumeration/count exists; do not infer it from search | [OpenAI Storage file screenshot](screenshots/openai/storage-file-details.png) plus read-only API metadata inspection below | **PARTIAL evidence / actual count UNKNOWN**; 37 completed files verified, but no authoritative chunk cardinality field in the retrieved API objects. Search results and parsed content cannot prove the total; keep `actual=null`. |
| E6 | One scheduled Render run with a public `last_run.json` | URL | Not started; G5 |
| E7 | Second-run delta: `added=0 updated=0 skipped=N` | Artifact history (gist revisions) | Not started |

E4 pass criteria (agreed during planning): ask in the **first turn** only, because follow-up turns with file search reportedly fail with “item not found” (ASSUMPTION, community report). The URL must belong to the article that actually covers YouTube, so check it against the `url` attribute of the cited file ([ADR-0002 §3](adr/0002-chunking-and-citation.md#3-citation-path-filename--zendesk-url)). A filename-only citation with no URL line **fails** E4.

**G3 read-only OpenAI evidence (VERIFIED 2026-10-31):** The [Storage / Files screenshot](screenshots/openai/storage-file-details.png) shows a `Ready` uploaded Markdown file, **not** the number of embedded chunks. API readback of vector store `vs_6ae554a891cc819190f1467052c2d696` returned `status=completed`, `file_counts.completed=37`, `file_counts.total=37`, `file_counts.failed=0`, and `usage_bytes=230978`. Listing its 37 attachments returned `status`, `usage_bytes`, and `chunking_strategy`, but **no exact chunk-count field**. Of these attachments, 36 reported static settings `4096/0` (size/overlap); one, `how-to-use-youtube-live-schedule-with-optisigns.md`, reported anomalous `0/0` on both list and retrieve. The anomaly is not explained and should not be silently treated as a measured chunk count. The file-content endpoint exposes parsed text blocks, not an exhaustive enumeration of embeddings. The implemented upload explicitly sends `chunking_strategy` to OpenAI ([source](../rillmark/vector_store.py)); it cannot force an undocumented response field to appear. `chunks.estimated=37` remains a **hypothesis**, and `chunks.actual=null` remains correct. See the [OpenAI Vector Stores reference](https://developers.openai.com/api/reference/resources/vector_stores/methods/list) and [Retrieval guide](https://developers.openai.com/api/docs/guides/retrieval).

## 4. Rules

- No result is written into the README or the artifact unless it was observed. `--dry-run` is not offline: it fetches Zendesk. Unknowns stay `null` or “not measured”; do not mark G3/E5 PASS on search samples, `tiktoken`, or the assumption that one file means one chunk. Escalate if the rubric demands actual chunks and the provider has no authoritative count.
- Live checks run only after G0, and stay within the cost approved by the project author (planning estimate: < $0.10 for the pilot, an ASSUMPTION to re-check against pricing).

## 5. Acceptance gates

- [ ] `pytest` green offline in < 10 s; runs in CI or locally (CI is optional).
- [ ] E1–E7 collected, or explicitly listed under “what I cut” in the README; E5/G3 remains UNKNOWN if an exact chunk count cannot be proven, not silently passed.
