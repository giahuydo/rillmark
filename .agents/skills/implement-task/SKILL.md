---
name: implement-task
description: Workflow for an implementer agent taking one Rillmark task card — read the contract, write tests first, implement inside the write scope, run the gates, and report with evidence. Use at the start of any coding task assigned to you.
---

# Implement a task

You implement; the integrator reviews, commits, and pushes. Read `AGENTS.md` and the `python-standards` skill before starting.

## 1. Task card (what you should receive)

A valid card names: **goal**, **phase**, **design sections** to follow (doc + §), **write scope** (exact paths), **acceptance checks**, **out of scope**, and **stop conditions**. If any of these is missing or contradicts the docs, stop and report `BLOCKED` with the question — do not guess.

## 2. Start

- Confirm the working directory is your assigned worktree/branch (`git branch --show-current`). Do not run git mutations.
- Re-read the cited design sections. List the contract items you will implement (inputs, outputs, errors, exit codes).
- Post a short `START` report: task, scope, plan in 3–5 bullets.

## 3. Build (test first)

1. Write the failing tests for the acceptance checks (offline, fakes, minimal fixtures).
2. Implement the smallest code that passes them, following `python-standards`.
3. Refactor only within your scope. Never touch files outside the write scope, even to fix something nearby — report it instead.
4. No paid API calls, no network in tests, no new dependency without a reason in the report.

## 4. Gate

Run and keep the output:

```bash
ruff format --check <changed paths>
ruff check <changed paths>
pytest <your test files> -q
git status --short          # proves only in-scope files changed
```

Then walk the `python-standards` §10 checklist.

## 5. Report

```
DONE <task>
Changed: <exact paths>
Contract: <doc §> → implemented items; deviations: <none | list with reason>
Gate: ruff format OK | ruff check OK | pytest N passed (paste summary lines)
Evidence labels: VERIFIED <what ran> / UNKNOWN <what could not be checked>
Open: <follow-ups, out-of-scope issues found>
```

Never claim a check passed unless its output is in the report. Set the task to review; never mark it done yourself.

## 6. Stop conditions

Stop and report `BLOCKED` when: the card is incomplete or conflicts with the docs, a fix needs files outside scope, a paid/live call would be required, a test can only pass by weakening the contract, or the same failure repeats after two honest attempts.
