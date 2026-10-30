# 00 — Requirements

Back to [docs index](README.md). Related: [01-architecture](01-architecture.md), [05-testing](05-testing.md), [phases](phases.md).

## 1. Source

The original take-home doc, read 2026-10-30. Part 1 is the “OptiBot Mini-Clone”, about 8 focused hours. Part 2 is the “SCIO Slice Plan” (about 10 hours, Brief A or B) and is **Deferred**: out of scope for this plan set. Both parts are submitted together, so Part 2 must still be scheduled separately (see [phases.md](phases.md#out-of-scope)).

Requirements and grading criteria are summarized from the supplied OptiSigns Fullstack Take-Home Test (accessed 2026-10-30). Quoted instructions and the required runtime prompt are attributed to that assignment.

The assignment is explicit about time: “If you run short, submit what you have and tell us what you cut.” This plan treats the **8-hour budget as a hard constraint**. Anything marked *bonus* below is cut first.

## 2. Functional requirements (from the assignment)

| ID | Requirement (paraphrased; quotes are verbatim) | Priority | Planned in |
|---|---|---|---|
| R1 | Pull **≥ 30 articles** from `support.optisigns.com` (hint: Zendesk API) | Must | [02](02-data-contracts.md#1-zendesk-input) |
| R2 | Convert each article to clean Markdown and save it as `<slug>.md` | Must | [02](02-data-contracts.md#2-markdown-file-contract) |
| R3 | “Preserve relative links, code blocks, and headings. Remove nav/ads.” | Must | [02](02-data-contracts.md#3-html--markdown-normalization-rules) |
| R4 | Via a **Python script**, upload Markdown to the vector store via API. “API upload is mandatory — no UI drag-and-drop here.” | Must | [01](01-architecture.md), [ADR-0001](adr/0001-ai-provider.md) |
| R5 | Attach files to the vector store. The chunking strategy is ours, but it must be **explained in the README** | Must | [ADR-0002](adr/0002-chunking-and-citation.md) |
| R6 | “Log how many files and chunks were embedded.” Report actual completed files (`file_counts.completed`), `chunks.estimated` with `chunks.basis`, and `chunks.actual = null`: the provider does not expose authoritative embedded chunk cardinality. Disclose this limitation in the root README; G3 remains **UNKNOWN**, and retrieval/citation checks do not prove chunk count. | Must; count limitation disclosed | [ADR-0002](adr/0002-chunking-and-citation.md#4-chunk-count-logging-gate-g3) |
| R7 | Create the assistant in the **OpenAI Playground UI** with the system prompt **verbatim** (§4) | Must | [ADR-0001](adr/0001-ai-provider.md) |
| R8 | Sanity check: ask “How do I add a YouTube video?” and take a **screenshot** showing a correct answer with citations | Must | [05](05-testing.md#3-acceptance-evidence) |
| R9 | Wrap the scraper-uploader in `main.py` and add a `Dockerfile` | Must | [04](04-operations.md#2-docker-contract) |
| R10 | `docker run -e API_KEY=... main.py` **runs once and exits 0** | Must | [04](04-operations.md#2-docker-contract) |
| R11 | Schedule it **once per day** on a public cloud platform | Must | [ADR-0004](adr/0004-scheduler.md) |
| R12 | The job re-scrapes, detects new/updated articles (hash, Last-Modified, …), and uploads **only the delta** | Must | [03](03-sync-lifecycle.md), [ADR-0003](adr/0003-sync-state.md) |
| R13 | Log counts: **added, updated, skipped**. Provide a link to job logs or the last run artefact | Must | [04](04-operations.md#4-logs-and-public-run-artifact) |
| R14 | GitHub repo with a **cryptic name** (no “optisigns”), clear commits, no hard-coded keys, `.env.sample` | Must | [04](04-operations.md#1-configuration) |
| R15 | README of **≤ 1 page**: setup, how to run locally, link to daily job logs, screenshot | Must | [04](04-operations.md#6-root-readme-deliverable-outline) |
| R16 | Tests | Bonus (+5) | [05](05-testing.md) |

Warm-up (not graded, done by the project author): create an optisigns.com trial account and chat with OptiBot; open an OpenAI platform account (done; see [ADR-0001](adr/0001-ai-provider.md)).

## 3. Rubric (pass bar 70 pts)

| Area | Pts | Plan emphasis |
|---|---|---|
| Scrape & clean quality | 25 | The largest area, so it gets the most phase time ([phases P1](phases.md#p1--scrape--markdown)). Fixture-tested HTML→Markdown rules. |
| API-based vector-store upload works | 20 | API-only upload, logged counts, store attached in Playground. Gates G1/G2. |
| Daily job deployment & logs | 15 | Render Cron plus a public `last_run.json` link |
| Code clarity + README | 10 | Small modules, ≤ 1-page README |
| Bonus tests | +5 | pytest on the converter and delta logic |

## 4. System prompt (verbatim, must not be edited)

```
You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply.
```

Copied character for character from the assignment doc, including the `•` bullets and straight quotes. It is pasted into the Playground unchanged. No additions go into the prompt itself. Any steering we need is done through the **data** (the `Article URL:` header, see [ADR-0002](adr/0002-chunking-and-citation.md)), never by rewording the prompt.

## 5. Assumptions

| ID | Assumption | Check at |
|---|---|---|
| A1 | **Resolved (VERIFIED discovery snapshot, 2026-10-30):** unauthenticated public API returned 13 categories, 74 sections and 416 non-draft `en-us` articles (HTTP 200 on all seven requests). Future availability is not guaranteed. | P1 snapshot complete |
| A2 | **Resolved (VERIFIED discovery snapshot, 2026-10-30):** article `360051014713` answers the YouTube question; selected sections `26324076807315`, `26324141467539`, `26324224269459` contain 37 distinct articles including it. Versioned selection: `config/selection.json` (`section_ids` = `[26324076807315, 26324141467539, 26324224269459]`, `youtube_article_id` = `360051014713`, `min_articles` = 30). | P1 snapshot complete |
| A3 | `API_KEY` in the docker command is the OpenAI key. We accept `API_KEY` and fall back to `OPENAI_API_KEY`. | P4 |
| A4 | Reviewers judge “correct answer with citations” from the screenshot, not from a live, persisted assistant (see the G4 risk) | Accepted |
| A5 | API credits are added before any API work (G0) | G0 |

## 6. Constraints

- Time: about 8 focused hours for Part 1 ([phases.md](phases.md)).
- No paid API call until G0 is cleared. No UI upload of files, ever.
- No database, Redis, or queue. Remote state lives in the vector store ([ADR-0003](adr/0003-sync-state.md)).
- For the author's Playground attachment, use a key scoped to its **same OpenAI project** (the one used by the Playground); a grader's key belongs to a different project and resolves or creates its own marked store ([ADR-0001](adr/0001-ai-provider.md#5-consequences)).
- Secrets come only from the environment. The repo ships `.env.sample` with placeholders only.

## 7. Out of scope

- Part 2, SCIO Slice Plan: **Deferred**.
- A custom chat UI or web app. The Playground is the assistant surface; an optional CLI query helper is a stretch goal only.
- Multi-locale content (English only), and articles behind login.
- Automatic source-absence deletion is deferred for the 8-hour budget: absent source articles are logged as `deletion_candidates` only, never detached/deleted because of absence. Replacement cleanup of an updated article's own old version remains in scope.

## 8. Acceptance gates for this doc

- [ ] Every Must row R1–R15 maps to a planned section and to a test or evidence item in [05-testing](05-testing.md#2-test-matrix).
- [ ] System prompt §4 diff-checked against the source doc at implementation time (zero diff).
- [x] A1/A2 resolved against the public API discovery snapshot; [ ] A3 verified at P4 with the literal Docker command after G0 (credits/key) is unblocked.
