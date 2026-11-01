# Risks and open questions

← [9. Estimate, and where AI coding assistants change it](09-estimate.md) · [Overview](README.md)

## 10. Risks

| Risk | Likelihood / impact | Mitigation | Fallback |
|---|---|---|---|
| Product later wants View to allow content changes (S2) | Low / low (SCIO's server enforces S1 today) | One predicate | Switch (0.5 day) |
| Business wants revoke to stop playback | Low / low (SCIO keeps the assignment) | Manifest builder already checks `canUseContent` | Strict variant (1 day) |
| Admin visibility is global, not per Team | Low / medium (Team Admin UI is Team-scoped) | Bypass scope is one condition | 1 day + matrix rows |
| Media edge cases (codecs, huge PDFs) | High / medium | Allowlist, timeouts, `failed` state | Page/size caps |
| Policy engine slips and blocks M3–M6 | Low / high | Built first, matrix from day 1 | Pull M7 out of core |
| AI-assisted velocity lower than forecast | Medium / low | Baseline is the commitment | Re-forecast at week 2 |
| Users expect SCIO's looser playlist display (hidden items shown in full) | Low / low | We show a placeholder; product decision recorded | Show name only (0.5 day) |

## 11. Open questions (don't block the start)

1. Replace or Delete of an Asset that a Screen or Playlist uses. Default: Replace keeps the ID; Delete is refused with `409 ASSET_IN_USE`.
2. Whether a Super Admin's view spans Teams. Default: account-wide, like the Owner.
3. Storage quota and upload size per plan, and whether quota is per Team or per account. Default: per Team, values from the plan table.
4. Exact reach of the "Everyone in the account" subject. Observed: such a folder appears in a Team B member's picker. Default: every member of any Team in the account. "Admin Only" is observed to cover the owning Team's admins only; a Team grant still covers all of that Team.
5. Whether SCIO's Download and Trash buttons work on a hidden playlist item, and what a physical player shows after a share is revoked. Neither changes our design (placeholder; D3b).

**Answered in the trial** (details in [§2](02-scio-today.md)): S1 is enforced on the server; revoking a share keeps the assignment; Move To Team lands in Home and clears the assignment; OnHold frees the slot and keeps the assignment; Read Only shows Download.

---

← [9. Estimate, and where AI coding assistants change it](09-estimate.md) · [Overview](README.md)
