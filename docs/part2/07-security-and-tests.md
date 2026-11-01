# 7. Security and tests

← [6. Key lifecycles](06-lifecycles.md) · [Overview](README.md) · [8. Milestones](08-milestones.md) →

**Threats covered:** ID guessing (tenant check + 404), leaks via lists/search/thumbnails/pickers (one shared predicate), role escalation (a role can only grant a subset of the granter's capabilities), stale sessions after removal, TOCTOU on assign/move/quota (row locks + in-transaction re-checks), pairing brute force and token theft, upload abuse, CSRF, audit tampering (no UPDATE/DELETE on `audit_event`).

**Testing:** a generated, table-driven matrix (role × grant × context Team × action, ~60 rows) for `authorize()`, plus API tests on seeded multi-Team fixtures, written **inside each milestone**. Representative cases:

| # | Case | Expected |
|---|---|---|
| N1 | B User, A's Asset folder shared to B at View, B Screen folder Edit; Edit Screen **and** Push | Both allowed, identical result |
| N2 | Same, Screen folder View only | Both denied, same reason |
| N3 | Share revoked while the picker is open | Save denied on re-check |
| N6 | Admin of A opens a B Screen by ID | 404 |
| N8 | User removed from B mid-session | Next B request 403 |
| N11 | Move into a full Team | 409 with the licence offer; nothing changed |
| N13 | Two pairings race for the last slot | Exactly one succeeds |
| N16 | Delete an Asset used by a Screen the actor can't see | 409, no names or counts leaked |
| N19 | Search term matches a hidden Asset | No hit, no count |
| N22 | Push to 3 Screens, 1 unauthorized | Whole batch rejected |
| N24 | Second client knows the pairing code but not the secret | 403 |
| N25 | Read Only member, Screen folder Edit; Edit Screen or Push | 403 (role checked before folder) |
| N26 | Open a playlist containing an Asset from a folder the viewer can't see | Placeholder only; the Asset's detail, thumbnail and download return 404 |
| N27 | Team Admin shares a folder to another Team or to the whole account | 403 |
| N28 | Move a Screen to another Team, then OnHold and back | Move clears the assignment; OnHold keeps it and frees the slot |

---

← [6. Key lifecycles](06-lifecycles.md) · [Overview](README.md) · [8. Milestones](08-milestones.md) →
