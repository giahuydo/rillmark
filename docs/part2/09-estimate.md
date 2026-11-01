# 9. Estimate, and where AI coding assistants change it

← [8. Milestones](08-milestones.md) · [Overview](README.md) · [10–11. Risks and open questions](10-risks-and-open-questions.md) →

**Three delivery levels** (prototype and lean figures are scoped estimates, not a full breakdown):

| Level | Calendar (2 eng.) | What it contains | What it leaves out |
|---|---|---|---|
| **Working prototype** | 2–3 weeks (~18 eng-days) | One account, built-in roles, folder View/Edit, image upload, browser pairing, Asset assignment via both paths, the core `authorize()` with its matrix | Invites, quotas, Move/OnHold, custom roles, Playlist/Schedule, hardening. A demo, not shippable |
| **Lean AI-assisted MVP** | 5–7 weeks (~44 eng-days + contingency) | All of Brief B except M7/M9 and polish; Asset-only assignment | Playlist/Schedule assignment (a disclosed BRIEF gap), apply-to-subfolders, UI polish |
| **Full MVP (committed)** | 8 weeks core, 9.5–10 with contingency (63 + 13) | Everything in [§3](03-scope.md), hardened and tested | — |

**AI-assisted forecast per milestone:** AI speeds up scaffolding, CRUD, forms and test generation. It speeds up very little where the time goes into deciding and verifying semantics.

| Milestone | Baseline | With AI | Where AI helps | What still needs an engineer |
|---|---:|---:|---|---|
| M0 Foundations | 5 | 4 | Scaffold, CI, compose, migrations | Session security review |
| M1 Teams & members | 7 | 5.5 | CRUD APIs, forms, email templates | Quota invariant under concurrency |
| M2 Policy engine | 6 | 5.5 | Generating matrix rows | The rules themselves; every row reviewed |
| M3 Folders & sharing | 7 | 6.5 | Tree CRUD, permission dialog UI | Snapshot semantics, locking |
| M4 Assets | 9.5 | 8 | Upload UI, API, worker skeleton | Storage reservation, file sniffing, failure paths |
| M5 Screens | 9 | 7.5 | Player UI, settings forms | Pairing security, capacity races, Move transaction |
| M6 Assignment | 5.5 | 5 | Two UI entry points | Locking and concurrency tests |
| M7 / M9 Playlist, Schedule | 8 | 6 | Mostly standard CRUD + player rendering | Partial-visibility rules |
| M8 Hardening | 6 | 6 | Drafting extra test cases | Running and judging them; performance work |
| **Core** | **63** | **≈ 54** | | |

- **Contingency stays at 13 days** even with AI, because it covers unverified product rules, not typing speed.
- **AI-assisted outlook:** ≈ 54 + 13 = 67 eng-days ≈ **7 weeks core, about 8.5 with contingency**. The critical chain drops to about 26.5 days on Engineer A.
- **How we keep it honest:** AI-generated code goes through the same review, and policy code gets two reviewers. At the **end of week 2** we compare actual against forecast for M0–M2: eng-days spent, review time, defects found, and matrix-test pass rate. Then we re-forecast. Until then **we commit to the baseline and treat the AI figure as a hypothesis to test**. Published studies on AI productivity range from noticeable gains to slowdowns on mature codebases, so we measure on this project rather than assume a fixed discount.

**Planning effort and what I cut:** this plan was produced within the BRIEF's ~10-hour planning budget, including hands-on SCIO use. To stay inside it I left out:

- **Trial checks not run:** Replace or Delete of an Asset that is assigned; whether a Super Admin's view spans Teams; whether the Download and Trash buttons SCIO shows for a hidden playlist item actually work; what a physical player shows after a share is revoked. Each has a fail-closed default in [§5](05-data-model-and-authorization.md) and an entry in [§11](10-risks-and-open-questions.md#11-open-questions-dont-block-the-start). The other rules the plan depends on (S1 on the server, role caps, Team Admin scope, inheritance, OnHold, Move To Team, revoke) were checked in the trial ([§2](02-scio-today.md)).
- **Plan detail not written:** a full API specification, UI wireframes and the complete negative-test matrix ([§7](07-security-and-tests.md) shows representative cases). These are week-1 work for the team.

---

← [8. Milestones](08-milestones.md) · [Overview](README.md) · [10–11. Risks and open questions](10-risks-and-open-questions.md) →
