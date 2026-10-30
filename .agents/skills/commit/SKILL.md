---
name: commit
description: Rillmark commit strategy and message standard for the integrator (single Git owner). Use before creating, splitting, merging, or pushing any commit — branch and merge flow, commit boundaries, title and body format derived from the task card, and the pre-commit gate script.
---

# Commit

Only the integrator commits, merges, and pushes (`AGENTS.md` §5). Implementers never run git mutations; they leave an uncommitted diff in their assigned worktree plus a `DONE` report.

## 1. Strategy

- **History:** linear `main`. Every commit on `main` builds, passes its tests, and leaves the docs truthful.
- **Unit of change:** one task card → one commit (one capability, its tests, and any doc it changes). Split a task into several commits only when the parts are independently meaningful (e.g. a refactor that enables the feature goes first).
- **Never mix** in one commit: unrelated fixes, formatting of untouched files, generated output, or local research.
- **Branches:** each implementer works on `task/<phase>-<slug>` in its own worktree (e.g. `task/p1-html-converter`). After `DONE`, the integrator enters that worktree, reviews the uncommitted diff, stages only approved in-scope paths, runs the gate, and creates the task commit there. It then rebases that clean, unpublished branch onto `main` if needed, reruns the checks after any conflict resolution, and fast-forwards `main`. No merge commits.
- **Before push:** local fixups are allowed (`git commit --fixup` + `git rebase -i --autosquash` locally). **After push:** never amend, rebase, or force-push; fix forward with a new commit.
- **Push cadence:** push after each integrated task so the public history mirrors progress. The first push of the repository always needs the project author's approval of the staged manifest and message.

## 2. Title

```
<type>(<scope>): <imperative summary>
```

- **Types:** `feat` new behavior · `fix` bug fix · `test` tests only · `refactor` no behavior change · `docs` documentation · `build` packaging, Dockerfile, deps · `ci` pipelines/schedules · `chore` repo tooling and config.
- **Scopes (closed list):** `config`, `zendesk`, `convert`, `store`, `sync`, `report`, `cli`, `docker`, `ops`, `readme`, `docs`, `tooling`. Omit the scope only when a commit truly spans the whole repo.
- **Summary:** imperative mood, lowercase first word, no trailing period, ≤ 72 characters for the whole title. Say what the repo can do after the commit, not what you did ("convert zendesk html to markdown", not "worked on converter").

### Deriving the title from the task card

Task cards are tracked privately and may be written in another language. The public commit carries **no task IDs, tool names, or assistant names**.

1. Take the card's **phase and module** → pick `type` and `scope` from the lists above.
2. Rewrite the card's goal as an English imperative capability (≤ 50 characters is ideal).
3. Keep the same wording for the same capability across commits (e.g. always "store resolution", never alternately "vector store lookup").
4. After pushing, record the commit SHA on the private task, so traceability stays private.

| Task card (private) | Commit title (public) |
|---|---|
| P1 — HTML → Markdown converter + fixtures | `feat(convert): convert zendesk article html to markdown` |
| P1 — fetch articles for configured selection | `feat(zendesk): fetch articles for the configured selection` |
| P2 — resolve marked vector store, upload files | `feat(store): resolve marked store and upload articles` |
| P3 — hash-based delta sync | `feat(sync): upload only new and changed articles` |
| P4 — Dockerfile one-shot run | `build(docker): run the sync once per container start` |
| P4 — publish last_run.json to Gist | `feat(ops): publish run summary to a public gist` |
| Plan docs update | `docs: align sync lifecycle with deferred deletion` |

## 3. Body

```
<title>

Motivation:
Why this change is needed now (1–3 lines, link the design section,
e.g. docs/03-sync-lifecycle.md §4).

Changes:
- What changed, grouped by area, written for a reader of the diff.

Verification:
- Exactly the checks that ran and their result, e.g.
  "ruff check: clean", "pytest tests/test_convert.py: 14 passed",
  "check_repo.py: PASS".

Known limitations:
- What is still open, unverified, or deliberately deferred.
  Write "None." if there is nothing.
```

- Wrap at 72 columns. English. Plain text with `-` bullets.
- Verification lists only commands that actually ran in this commit's state. Never write "tested" without the command and result.
- No trailers for AI attribution, bots, or co-authors. No emoji. No internal tracking IDs.
- Small `docs`/`chore` commits may collapse the body to a short paragraph, but must still state verification.

## 4. Gate (run every time)

```bash
git status --short
git add <explicit paths>                       # never `git add .`
git diff --cached --check
git diff --cached --stat
python3 .agents/skills/commit/scripts/check_repo.py --staged
pytest <tests for the staged code> -q          # when code is staged
ruff format --check <staged py> && ruff check <staged py>
```

`check_repo.py` fails on broken Markdown links/anchors, a changed system prompt, secret-like strings, and public-hygiene markers in `README.md`/`docs/`.

Then: `git commit` with the message from a file (`git commit -F <msg>`), `git show --stat HEAD`, and push only per §1.

## 5. Never stage

`research/`, `.env*` (except `.env.sample`), `out/`, `last_run.json`, scraped corpus files, full raw help-center articles, editor/agent caches.
