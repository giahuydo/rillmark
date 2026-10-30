# Agent Rules — Rillmark

Single source of rules for every coding agent working in this repository. Tool-specific files (`CLAUDE.md`, skills, MCP configs) only point here. If a user-level or global instruction conflicts with this file, this file wins inside this repository.

## 1. Project

- Part 1 take-home: scrape ≥ 30 Zendesk help articles → Markdown → OpenAI Vector Store (API upload) → daily Docker job with delta sync. Budget: ~8 focused hours.
- The design is in [`docs/`](docs/README.md). Read `docs/README.md` first, then the doc for your area. The docs are the contract; change them only through a reviewed doc task.
- Stack: Python 3.12, `pytest`, pinned `requirements.txt`, `python main.py` runs once and exits. No database, queue, or web server.

## 2. Phase boundaries

Work only inside the phase you were assigned ([`docs/phases.md`](docs/phases.md)).

| Phase | Scope | Paid API? |
|---|---|---|
| P1 | Zendesk fetch, HTML → Markdown, `--dry-run`, converter tests | No |
| P2 | Store resolution + upload, `--limit` pilot | Yes, after G0 and owner approval |
| P3 | Delta sync | Yes (live checks only) |
| P4 | Docker, Render Cron, Gist publisher | Yes |
| P5 | Root README, screenshot, public hygiene | Only for a new live screenshot, after G0 and approved cost; README/hygiene and reuse of existing evidence need no paid call |

Never call OpenAI or any other paid API unless the owner has approved that run and its cost.

## 3. Non-negotiables

- The OptiBot system prompt in [`docs/00-requirements.md` §4](docs/00-requirements.md#4-system-prompt-verbatim-must-not-be-edited) is verbatim. Do not edit it anywhere.
- Every **generated article** Markdown file, including each split part, starts with `# {title}` then exactly one `Article URL: {html_url}` line ([02 §2](docs/02-data-contracts.md#2-markdown-file-contract)). Project docs and skills keep their own formats.
- Never select a vector store by display name. Use the `managed_by` marker contract ([01 §3](docs/01-architecture.md)).
- Never call the global `DELETE /files/{id}`. Only detach from the resolved store.
- `chunks.actual` stays `null` unless an authoritative count exists. Never present an estimate as actual.

## 4. Evidence and reporting

- Label claims **VERIFIED** (observed in this run), **DOCUMENTED** (official docs), **ASSUMPTION**, or **UNKNOWN**.
- Never report PASS without the command and output that prove it. A skipped check is reported as skipped.
- Report the changed files, the commands that were run, and their results.

## 5. Roles and concurrency

| Role | May | Must not |
|---|---|---|
| **Integrator** (single Git owner) | Stage explicit paths, commit, push, merge worktree branches | Commit without the owner approving public content |
| **Implementer** | Edit files inside the assigned write scope, run scoped tests | Run any git mutation (`add`, `commit`, `push`, `reset`, `stash`), edit outside scope |
| **Reviewer** | Read everything, report findings with `file:line`, severity, fix | Edit files |

- Parallel agents get disjoint write scopes. Once `main` has a commit, each implementer works in its own git worktree/branch, and only the integrator merges (fast-forward only).
- Respect the machine's agent limit. Do not start extra agents to go faster.

## 6. Git conventions (integrator)

The full strategy, title derivation, body template, and gate are in the `commit` skill (`.agents/skills/commit/`). In short:

- One task → one commit on a linear `main`. Implementers work on `task/<phase>-<slug>` worktree branches; the integrator fast-forwards.
- Title `type(scope): imperative summary` (≤ 72 chars) from the closed type/scope lists. Body: **Motivation**, **Changes**, **Verification**, **Known limitations**, wrapped at 72. Only list verification that actually ran.
- No AI attribution trailers, bot signatures, emoji, or internal tracking IDs.
- Stage explicit paths (never `git add .`). Never amend, rebase, or force-push after a push.

Code style and tests follow the `python-standards` skill. Implementers follow the `implement-task` skill.

## 7. Tests

- Unit tests run offline: no network and no API keys. HTTP and SDK calls sit behind thin modules that tests replace with fakes.
- Run only the tests for what you changed (`pytest tests/test_x.py -q`). Do not run slow or live suites without approval.

## 8. Secrets, privacy, content rights

- Keys come only from the environment. `.env` is git-ignored. `.env.sample` holds placeholders only. Never print or log a key.
- Do not commit the scraped article corpus or full raw help-center articles. Test fixtures are minimal HTML snippets per pattern, each citing the source article ID.
- Public files (`README.md`, `docs/`) contain no internal tracking IDs, assistant/tool names, private notes, or account details.
- `research/` is local working material and is never committed.

## 9. Tooling

How each runtime loads these rules, skills, and MCP servers, and what was verified, is in [`.agents/TOOLING.md`](.agents/TOOLING.md).
