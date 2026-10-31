# Rillmark — Plan Docs (Part 1: OptiBot Mini-Clone)

- **Status (2026-10-31):** Docker cloud dry-run, live OpenAI delta sync and public Gist publication **VERIFIED**. GitHub Actions daily schedule is enabled; the first schedule-triggered run is **PENDING**. [Playground answer screenshot](screenshots/openai/optibot-youtube-playground.png) captured; explicit first-turn `Article URL:` remains outstanding.
- **Date:** 2026-10-30
- **Owner:** project author (decisions).
- **Source of truth for the assignment:** the original take-home doc, read on 2026-10-30. Internal decision evidence is tracked separately from public deliverables.
- **Scope:** Part 1 (build) only. Part 2 (SCIO Slice Plan) is **Deferred** and not covered here.

> These documents describe the design and implementation plan. The ≤ 1-page **repo-root `README.md`** is a separate deliverable, outlined in [04-operations.md](04-operations.md#6-root-readme-deliverable-outline) and scheduled for implementation.

## Locked direction

| Topic | Decision | Where |
|---|---|---|
| AI provider | OpenAI (not Gemini): Vector Store via API, Playground Chat + File search for the assistant | [ADR-0001](adr/0001-ai-provider.md) |
| Source | Zendesk Help Center API (`support.optisigns.com`), ≥ 30 English articles from coherent sections, including the YouTube article | [00](00-requirements.md), [02](02-data-contracts.md) |
| Language | Python, single `main.py` entrypoint, Docker | [01](01-architecture.md) |
| Query API | Responses API + `file_search` (Assistants API is shut down) | [ADR-0001](adr/0001-ai-provider.md) |
| Chunking & citations | One Markdown file per article with an `Article URL:` header; static chunk size so each file fits in one chunk | [ADR-0002](adr/0002-chunking-and-citation.md) |
| Sync state | `sha256("v{schema_version}\nchunk={max}/{overlap}\n" + normalized_markdown)` in owned vector-store file attributes; store ownership uses vector store `metadata.managed_by = "rillmark-optibot-v1"`. No database. | [ADR-0003](adr/0003-sync-state.md) |
| Scheduler | GitHub Actions (Docker) daily; live cloud sync and public Gist verified, schedule-triggered execution pending | [ADR-0004](adr/0004-scheduler.md) |

## Docs index

| # | Doc | What it answers |
|---|---|---|
| 00 | [Requirements](00-requirements.md) | What the assignment asks, the rubric, must-have vs bonus, and what is out of scope |
| 01 | [Architecture](01-architecture.md) | Components, data flow, OpenAI resources, module layout |
| 02 | [Data contracts](02-data-contracts.md) | Zendesk input fields, Markdown file format, vector-store attributes, `last_run.json` |
| 03 | [Sync lifecycle](03-sync-lifecycle.md) | Hash, remote state, delta classification, safe update order, recovery and dedup |
| 04 | [Operations](04-operations.md) | Config/env, Docker contract, GitHub Actions, logs and public artifact, root README outline |
| 05 | [Testing](05-testing.md) | Test matrix, acceptance evidence (including the YouTube citation screenshot) |
| — | **[Engineering decisions & alternatives](engineering-decisions-and-alternatives.md)** | OpenAI/GitHub Actions rationale, trade-offs and [optional StrangeLoop agent demo + six screenshots](engineering-decisions-and-alternatives.md#3-beyond-scope-independently-developed-agent-workflow) (not a replacement for required deliverables) |
| — | [Phases](phases.md) | Sequencing, estimates, and the gate at the end of each phase |
| ADR | [0001 AI provider](adr/0001-ai-provider.md) · [0002 Chunking & citation](adr/0002-chunking-and-citation.md) · [0003 Sync state](adr/0003-sync-state.md) · [0004 Scheduler](adr/0004-scheduler.md) | Decisions with alternatives and consequences |

## Evidence labels used in every doc

| Label | Meaning |
|---|---|
| **VERIFIED (manual UI check)** | Reported by the project author from a manual provider UI check (screenshots, 2026-10-30); the screenshots were not inspected directly when this planning evidence was recorded. |
| **VERIFIED (browser check)** | Observed directly in a browser session during planning (2026-10-30). |
| **DOCUMENTED** | Stated in official provider docs (checked 2026-10-30). Not yet exercised on this project. |
| **ASSUMPTION** | Reasonable belief, not yet confirmed. Must be checked at the named gate. |
| **UNKNOWN** | No evidence yet. Must not be reported as a result. |

## Open gates (blocking, tracked in [phases.md](phases.md#open-gates-register))

| ID | Gate | Status | Owner |
|---|---|---|---|
| G0 | API-funded OpenAI ingestion and a real cloud sync are operational; this does not by itself establish the separate Playground screenshot requirement. | **VERIFIED for ingestion** (2026-10-31) | Owner |
| G1 | A store created via the API shows up in the Playground picker and attaches end to end | **PARTIAL:** Playground File Search returned an uploaded-file citation; store ID is not visible in the screenshot ([evidence](screenshots/openai/optibot-youtube-playground.png)). | Owner |
| G2 | “How do I add a YouTube video?” returns a grounded answer with the correct `Article URL:` line, with a screenshot | **PARTIAL:** first-turn answer and file citation captured, but explicit `Article URL:` line is missing ([evidence](screenshots/openai/optibot-youtube-playground.png)). | Owner |
| G3 | OpenAI API readback confirms 37 completed attachments, but does not expose their exact embedded chunk count. Log `files.actual`, `chunks.estimated` and its basis; keep `chunks.actual=null`. See [Storage screenshot](screenshots/openai/storage-file-details.png) and [API inspection notes](05-testing.md#3-acceptance-evidence). | **VERIFIED files / UNKNOWN actual chunks** (2026-10-31) | Implementation |
| G4 | Saved prompt (“New prompt” draft) deprecated; **shutdown 2026-11-30** (DOCUMENTED) | Risk accepted with mitigation | Owner |
| G5 | Public GitHub Gist publisher validated against a successful cloud live sync; the first schedule-triggered run still needs separate verification. | **VERIFIED live publish; scheduled evidence PENDING** | Owner + implementation |
| G6 | All 416 article bodies were surveyed and ten fixtures saved; iframe/figure/wrapper/NOTE/Unicode gaps mapped to conversion rules. Future input shapes and actual converted output remain unverified. | **Mostly resolved** by snapshot; P1 converter checks remain | Implementation |

**Docker bootstrap contract:** [04 §2](04-operations.md#2-docker-contract) specifies `docker run -e API_KEY=... <image> main.py`. Docker build and dry-run passed locally and on GitHub-hosted runners; a real Docker cloud sync passed on 2026-10-31. The exact literal local command with a live API key has not been independently verified. The image carries non-secret `config/selection.json`: `section_ids` = `[26324076807315, 26324141467539, 26324224269459]` (VERIFIED 37-article discovery snapshot), `youtube_article_id` = `360051014713`, `min_articles` = 30. `SECTION_IDS`/`YOUTUBE_ARTICLE_ID` optionally override. Sync with `VECTOR_STORE_ID` set retrieves it and requires vector store `metadata.managed_by = "rillmark-optibot-v1"`, else fails closed. Without ID, list all pages in the key's project and filter on this marker: 0 → create named `rillmark-optibot` with marker and no `expires_after`; 1 → reuse; >1 → fail closed. Never match by display name. File-attribute marker remains `managed_by = "rillmark-optibot-v1"`. No `--init-store`. A grader's separate-project key creates its own marked store. GitHub Actions runs the image directly; see [scheduler decision](adr/0004-scheduler.md).
