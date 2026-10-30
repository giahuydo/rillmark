# ADR-0002 — Chunking Strategy, Citation Path, and Chunk-Count Logging

Back to [docs index](../README.md). Related: [02-data-contracts](../02-data-contracts.md#2-markdown-file-contract), [05-testing](../05-testing.md#3-acceptance-evidence), [ADR-0001](0001-ai-provider.md).

- **Status:** Accepted with open gates G2, G3 (validated in [P2](../phases.md#p2--upload--validation-3-articles--all))

## 1. Context

- The verbatim system prompt says "Cite up to 3 "Article URL:" lines per reply". The model can only cite a URL that appears **in the retrieved chunk text**.
- Playground citation chips show the **filename** (`file_citation` → `filename`), not a URL (DOCUMENTED). The URL therefore has to be in the content.
- OpenAI's default chunking is 800 tokens with 400 overlap (DOCUMENTED). With a URL header only at the top of the file, every chunk after the first lacks the URL. Long articles would then be answered without a citable URL, or with an invented one.
- The assignment requires "Log how many files and chunks were embedded". Neither the vector-store file object nor the store reports a chunk count (DOCUMENTED).

## 2. Decision

1. **One file per article by default**, starting with `# {title}` and `Article URL: {html_url}` ([02 §2](../02-data-contracts.md#2-markdown-file-contract)). Count distinct selected articles separately from uploaded part-files.
2. **Static chunking**, with `max_chunk_size_tokens` set from the P1 converted Markdown distribution (largest **serialized file, header included**, plus 15% margin), capped at 4096. `chunk_overlap_tokens` is the minimum allowed (0 if accepted, else smallest valid; check in P2). Before upload, enforce the per-file serialized token budget including header; an oversize file fails the run with a clear error, never silently truncates. The VERIFIED primary selection has 37 articles, extracted body-text max 1,431 words; **ASSUMPTION** `tokens ≈ words × 1.35` gives max ≈1,932 (~1.9k) tokens, **not** measured Markdown tokens. Header/conversion can add tokens, so P1 must measure.
3. Default split path is **cut** for the 8 h budget. Build the H2-split fallback only if P1 measurement shows it is needed. In that conditional fallback, split at H2 into `<slug>--p<n>.md`; each part repeats the H1 and `Article URL:` line, and each serialized part must pass the same budget check. Unsplit key = `article_id/part` with part 1.
4. Intended invariant: **every retrieved chunk should carry its article URL** if each part really fits into one provider chunk. Internal provider tokenization is undocumented, so this is a hypothesis until the evidence gate below; do not claim it as observed.

Tokens are measured with `tiktoken` `o200k_base`. The tokenizer OpenAI uses internally for chunking is **not documented**, which is why the margin exists.

## 3. Citation path: filename → Zendesk URL

```
retrieved chunk text ──contains──▶ "Article URL: https://support.optisigns.com/hc/en-us/articles/…"
        │                                         │
        │ file_citation.filename = <slug>.md      │ model copies the line (system prompt rule)
        ▼                                         ▼
   Playground chip                         answer text (what the screenshot shows)
```

- The filename is a readable `<slug>.md`, so the chip and the URL point to the same article.
- Verification (E4): the URL in the answer must equal the `url` attribute of the cited file ([02 §4](../02-data-contracts.md#4-vector-store-file-attributes)). If the answer has no `Article URL:` line, the check fails.
- **Rejected:** adding citation instructions to the prompt (the prompt must stay verbatim), and putting the URL only in the filename or attributes (the model does not see attributes).

## 4. Chunk count logging (gate G3)

| Field | Meaning | When it is filled |
|---|---|---|
| `counts.selected` | Distinct selected Zendesk articles | After complete source selection; not a file or chunk count |
| `files.actual` | Actual completed store files (`file_counts.completed`), including foreign attachments; not an embedded-chunk count | After provider observation; `store.managed_files_completed` separately counts only owned completed file attachments |
| `chunks.estimated` | Tokenizer-based estimate per completed managed part-file using `ceil(max(0, tokens − overlap) / (max − overlap))`, minimum 1 | Only when the file token sizes and effective chunk settings are known; otherwise `null` |
| `chunks.basis` | `single-chunk-invariant` only as a **hypothesis** when each part is below the planned budget; otherwise `tiktoken-estimate` | Report alongside estimate and uncertainty, not as proof |
| `chunks.actual` | Provider-observed exact embedded chunk count | **`null` in this plan; G3 stays UNKNOWN.** Never copy estimated files/chunks or search hits. |

**Evidence gate (P2, E5, requires G0 and owner-approved cost).** Record the actual uploaded file IDs, their completed statuses, effective chunking settings (read back per attachment if available), source byte/token lengths, and any provider documentation/API field that might expose exact chunk cardinality. For each pilot part-file (at least three, including the longest and an H2 split if one exists), search with distinct beginning/middle/end phrases and compare returned content with the header and source; include query/result IDs and any pagination/limit. A full-text match supports but does **not prove** one chunk: search is ranked and may omit chunks. Partial matches or missing URL invalidate the proposed invariant and require adjusting/splitting then retesting. Before claiming G3 PASS or filling `chunks.actual`, obtain reproducible, authoritative exact per-file chunk counts (or a documented provider method that enumerates **all** embedded chunks), and reconcile the sum with the completed managed file IDs. If no such method exists, G3 remains **UNKNOWN / rubric risk** even when search and token estimates look good; escalate the acceptance gap to the project author rather than invent a count. Keep `chunks.actual=null`, mark E5 as evidence for retrieval only, and document the limitation in submission evidence.

Honest log wording: "`A selected articles; F completed managed files (including H2 parts); estimated ≈C chunks (basis: tokenizer/config hypothesis; max=X; largest=Y tokens). Actual embedded chunk count UNKNOWN: provider does not expose an authoritative count here.`" Never print `C` if required inputs are unavailable.

## 5. Consequences

- Retrieval granularity is per article by default (37 in the primary discovery snapshot). Oversize serialized files fail clearly; H2 split is only a conditional P1 fallback, not a default implementation.
- Changing max chunk size or overlap forces re-upload via `sha256("v{schema_version}\nchunk={max}/{overlap}\n" + normalized_markdown)` ([03 §2](../03-sync-lifecycle.md#2-state-model)); no manual schema bump is required for chunk changes.
- G2 and G3 stay **UNKNOWN** until P2 runs with credits.
