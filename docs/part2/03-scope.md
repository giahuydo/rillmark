# 3. Scope

← [2. How SCIO works today (from using it)](02-scio-today.md) · [Overview](README.md) · [4. Architecture](04-architecture.md) →

**In scope:** Account Members (add, invite, change role, remove from Team vs delete user), multiple Teams with Screen limits, the five default roles + custom roles, folder sharing with View/Edit per folder family, uploaded images/videos/PDFs (search, preview, download, duplicate, replace, delete, settings, plan limits), Screen pairing, folders, settings, OnHold, Move To Team, and assignment of an Asset, a minimal Playlist or a minimal Schedule through both entry points. An append-only audit log.

**Decisions the brief leaves open:**

| Topic | Decision | Why |
|---|---|---|
| Team | 2 full-stack engineers (one backend-leaning, one frontend-leaning) + 0.5 QA | The critical path is the policy chain; a third engineer saves at most about a week ([§8](08-milestones.md)) |
| Portal platform | Desktop web, current Chrome, Edge, Safari and Firefox; responsive down to tablet, phone layout not polished | SCIO admins manage content from a desktop; permission screens are table-heavy |
| Player platform | One browser player (any device with a modern browser, including a TV browser or a PC on kiosk mode) | Makes pairing, device tokens and assignment real without native builds; playback isn't the focus of Brief B |
| Depth | Deep on authorization, folders and assignment; shallow on media processing and player features | That is where Brief B's risk is |

**Non-goals (with reason):**

| Excluded | Why |
|---|---|
| Content Proposal / Approval | BRIEF |
| Apps, Designer, feeds | BRIEF limits Assets to uploaded files |
| Full Playlist / Schedule authoring | Brief A; we build only what assignment needs |
| Native players, offline cache, device fleet | Playback isn't the focus (BRIEF); a browser player makes pairing real |
| Office conversion, audio, streaming manifests | Needs a conversion service; PDF covers "documents" in MVP (a stated difference from SCIO) |
| Billing, SSO/MFA, API keys, bulk tag push, Live/Expire | Separate projects or separate time mechanisms |

---

← [2. How SCIO works today (from using it)](02-scio-today.md) · [Overview](README.md) · [4. Architecture](04-architecture.md) →
