---
name: python-standards
description: Rillmark Python coding standards (Python 3.12). Use whenever writing or reviewing Python in this repo — module layout, typing, formatting and lint (ruff), errors, logging, HTTP, configuration, determinism, and pytest conventions.
---

# Python standards

These rules apply to every Python file. `AGENTS.md` sets scope and safety; this skill sets how code is written. When a rule here and the design docs disagree, the docs win; flag the conflict in your report.

## 1. Tooling (enforced, not optional)

The first code commit adds this to `pyproject.toml`; until then use the same settings on the command line.

```toml
[project]
name = "rillmark"
requires-python = ">=3.12"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM", "RUF", "PTH", "S", "N"]
ignore = ["S101"]            # assert is fine in tests

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S", "PLR2004"]

[tool.pytest.ini_options]
addopts = "-q --strict-markers"
testpaths = ["tests"]
```

Gate before reporting done (all must pass, output pasted in the report):

```bash
ruff format --check rillmark tests main.py .agents
ruff check rillmark tests main.py .agents
pytest <the test files for your change> -q
```

Dev tools live in `requirements-dev.txt` (`ruff`, `pytest`). Runtime deps in `requirements.txt`, pinned with `==`. Do not add a dependency without saying why in the report.

## 2. Layout

```
main.py                    # CLI only: parse args, call rillmark.cli.run(), sys.exit(code)
rillmark/
  config.py                # env + config/selection.json → frozen dataclass
  zendesk.py               # HTTP fetch (thin, no parsing logic)
  convert.py               # HTML → Markdown (pure)
  state.py                 # hashing, delta classification (pure)
  vector_store.py          # OpenAI SDK wrapper (thin)
  report.py                # counts, chunk estimate, last_run.json (pure build + thin writer/publisher)
  models.py                # shared dataclasses / enums
tests/
  fixtures/                # minimal HTML snippets with source article ID
  test_<module>.py
```

- **Pure core, thin edges.** Conversion, hashing, classification and report calculations are pure: no I/O, no env, no network. `zendesk`, `vector_store`, and the `report.py` file-writer/publisher are thin injectable edges that only translate between the outside world and `models`.
- One responsibility per module. If a function needs a comment saying "and also", split it.
- No module-level side effects (no network or env reads at import time).

## 3. Style

- Type hints on every function signature and module-level constant. Use built-in generics (`list[str]`, `dict[str, int]`, `X | None`).
- Data contracts are `@dataclass(frozen=True, slots=True)` in `models.py`. Use `enum.StrEnum` for closed sets (sync class, run status, mode). No loose dicts across module boundaries.
- Names: `snake_case` functions/variables, `PascalCase` classes, `UPPER_CASE` constants. Verbs for functions (`classify_delta`), nouns for data (`ArticleDoc`).
- Functions stay short (aim ≤ 40 lines) with early returns. No nested functions beyond one level.
- Docstrings: one line on every public function stating what it returns or guarantees; add an `Args`/`Raises` block only when it is not obvious.
- Comments explain *why*, never restate *what*. No commented-out code, no `TODO` without an owner/phase.
- `pathlib.Path` for paths. f-strings for formatting. No wildcard imports.

## 4. Errors and exit codes

- Define narrow exceptions in `rillmark/errors.py` (`ConfigError`, `SelectionError`, `StoreResolutionError`, `UploadError`, `PublishError`).
- Raise at the edge where the fact is known; catch only where you can act (per-article loop records the failure and continues; top-level `run()` maps to the exit codes in [`docs/03-sync-lifecycle.md` §6](../../../docs/03-sync-lifecycle.md)).
- Never `except Exception: pass`. A broad `except` is allowed only in `run()` to log, record `failed`, and exit 1.
- Fail closed: ambiguous store resolution, missing config, or an incomplete fetch stops all provider-store mutations. Still record and publish safe failure metadata best effort, as the operations contract requires ([04 §4](../../../docs/04-operations.md#4-logs-and-public-run-artifact)).

## 5. Logging and output

- `logging` with one configured handler in `cli.py`; modules use `logger = logging.getLogger(__name__)`.
- One structured line per article action, e.g. `action=updated article_id=360051014713 file_id=file-… ms=812`, and one final `summary …` line ([04 §4](../../../docs/04-operations.md#4-logs-and-public-run-artifact)).
- Never log secrets, full HTTP headers, request bodies, or raw article HTML. `print` only in `main.py`.

## 6. HTTP and SDK calls

- Every request has an explicit timeout (connect 5 s, read 30 s). Retry only idempotent GETs and only on 429/5xx, with bounded exponential backoff (max 3 tries) honouring `Retry-After`.
- Follow pagination until the provider says there is no next page; a partial page set is an incomplete fetch, not an empty result.
- Wrap the OpenAI SDK in `vector_store.py` behind a small protocol class so tests use an in-memory fake. Pin the SDK version; check current method names with Context7 (`/openai/openai-python`) before using them.

## 7. Configuration

- `config.py` reads env once and returns a frozen `Config`. Precedence: env override → `config/selection.json` → defaults. Accept `API_KEY` then `OPENAI_API_KEY`.
- Validate on load (types, ≥ 30 selection, YouTube ID present) and raise `ConfigError` with an actionable message.
- `--dry-run` must work with no OpenAI key set.

## 8. Determinism

- Conversion output is byte-stable for the same input: LF line endings and one trailing newline. Apply NFC, NBSP conversion and zero-width removal **outside code only**; preserve inline/fenced code content and whitespace per [`docs/02-data-contracts.md` §3](../../../docs/02-data-contracts.md#3-html--markdown-normalization-rules). Sort only where order is not meaningful. The hash input follows [03 §2](../../../docs/03-sync-lifecycle.md#2-state-model) exactly.
- No timestamps or random values inside generated Markdown.

## 9. Tests

- pytest, offline, no keys, no network (a test that needs the network is a bug). Use fakes, not `mock.patch` on internals.
- Name tests `test_<behavior>_<condition>` and use the arrange / act / assert layout. One behavior per test; parametrize variants.
- Fixtures are minimal HTML snippets (one pattern each) in `tests/fixtures/`, with the source article ID in the file or a comment. No full raw articles.
- Every bug fix adds a test that fails before the fix.
- Golden files allowed for converter output; regenerate only on purpose and review the diff.

## 10. Review checklist (implementer self-check, reviewer verifies)

- [ ] Scope: only files in the task's write scope changed.
- [ ] `ruff format --check`, `ruff check`, scoped `pytest` all pass (output in the report).
- [ ] Types on all signatures; contracts are dataclasses/enums; no dicts across modules.
- [ ] Pure modules do no I/O; network calls have timeouts and bounded retries.
- [ ] Errors are narrow, fail closed, and map to the documented exit codes.
- [ ] No secrets, PII, or raw article bodies in code, logs, fixtures, or output.
- [ ] Behavior matches the design doc section cited in the task; any deviation is reported, not silently made.
