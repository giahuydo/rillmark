# SCIO Slice Plan — Brief B: Teams, Roles, Permissions, Assets and Screens

> **Chosen brief: B** (Team, Roles, Permissions, Assets and Screens) · 2026-11-01. This is the plan I would hand to the team before writing the first line of code.

## 1. Summary

| | |
|---|---|
| **What** | A multi-Team management portal plus a thin browser player. It answers one question everywhere: *who can do what to which Screens and files*. |
| **How** | A modular monolith (TypeScript API + React SPA), PostgreSQL, private S3-compatible storage and a Postgres job queue. One server-side `authorize()` decides every read and write; one `AssignContent` command serves both Edit Screen and Push to Screen. |
| **Order** | Foundations → policy engine → folders → Assets ∥ Screens → assignment → minimal Playlist and Schedule → hardening. |
| **How long** | **Committed:** 63 core eng-days + 13 contingency, 2 engineers + 0.5 QA → **8 weeks core, 9.5–10 with contingency.** **AI-assisted forecast:** ≈ 54 core days → about 7 weeks core, re-forecast with measured data after week 2 ([§9](09-estimate.md)). An earlier working prototype is possible in 2–3 weeks. |
| **Why this shape** | The risk in this slice is authorization semantics, not volume. The policy engine is built first, and each rule we could not fully verify in SCIO sits behind one named predicate. A new finding changes one function, not the design. |

**Evidence labels:** **BRIEF** (the take-home) · **DOCUMENTED** (OptiSigns Help Center) · **VERIFIED UI** (seen in our own SCIO trial; the role used is noted when it matters) · **VERIFIED API response** (the reply to SCIO's own web-app call, read in the browser) · **MANUAL CHECK** (done by hand in the trial, no screenshot kept) · **INFERRED** · **UNKNOWN** · **PROPOSED** (our design, never a claim about SCIO internals).

## Contents

| Page | What it covers |
|---|---|
| [2. How SCIO works today (from using it)](02-scio-today.md) | What we observed in a real SCIO trial, with evidence labels, and what is still unknown |
| [3. Scope](03-scope.md) | In scope, decisions the brief leaves open (team, platforms, depth), non-goals |
| [4. Architecture](04-architecture.md) | Modular monolith, file storage (blobs, previews, quota), queue; rejected alternatives |
| [5. Data model and authorization](05-data-model-and-authorization.md) | Entities, `authorize()`, folder permission bits, decisions D2–D5 |
| [6. Key lifecycles](06-lifecycles.md) | Upload, pairing, Move To Team, assignment (Edit Screen and Push) |
| [7. Security and tests](07-security-and-tests.md) | Threats and representative negative tests |
| [8. Milestones](08-milestones.md) | M0–M9, dependency graph, Gantt calendar, critical path, cut order |
| [9. Estimate, and where AI coding assistants change it](09-estimate.md) | Three delivery levels, AI-assisted forecast, planning effort and what was cut |
| [10–11. Risks and open questions](10-risks-and-open-questions.md) | Risks with fallbacks; questions that do not block the start |

---

[2. How SCIO works today (from using it)](02-scio-today.md) →
