# ADR-0004 — Scheduler: cron-job.org dispatch + GitHub Actions + public Gist

Status: Accepted (amended 1 Nov 2026). Supersedes the earlier Render Cron decision and the original "GitHub schedule only" trigger.

**Where the job runs:** `.github/workflows/rillmark-daily.yml` on a GitHub-hosted Ubuntu runner. It builds the existing Dockerfile, runs the non-root application once, preserves its exit code, and copies the report even after failure. No registry or Render service is required.

**What triggers it every day:**

| Trigger | When | Role |
|---|---|---|
| cron-job.org calls the `workflow_dispatch` API with `{"ref":"main","inputs":{"mode":"sync","trigger":"cron-job.org"}}` | 03:23 UTC daily | **Primary** |
| GitHub `schedule`, `47 3 * * *` | 03:47 UTC daily | **Standby, off.** `RILLMARK_SCHEDULE_ENABLED=false`, so the job is skipped and nothing runs twice. Set it to `true` only if cron-job.org is unavailable |
| Manual dispatch (default `dry-run`) | On demand | Operator checks |

The run name shows the trigger: `Rillmark daily (cron-job.org)`, `(github-schedule)` or `(manual)`.

**Why an external scheduler:**
- **GitHub's schedule is late or missing.** GitHub documents that `schedule` "can be delayed during periods of high loads… High load times include the start of every hour… some queued jobs may be dropped". On 1 Nov 2026 the 03:00 UTC daily slot was delivered **7 h 18 min late** (10:17 UTC). A fresh private probe repo with `*/5 * * * *` produced **no** `schedule` run in 45 minutes. The same probe dispatched by cron-job.org every five minutes ran on time each time (see [scheduler evidence](../04-operations.md#scheduler-evidence-1-nov-2026)).
- **Free and reliable.** cron-job.org is free, sends any HTTP method with custom headers and a JSON body, and keeps an execution history with response codes.
- **Alternatives cost money or add a service.** Render Cron Jobs have a minimum charge of $1 per cron job service per month; DigitalOcean, Railway and Fly.io generally need a paid or trial-credit plan to keep a recurring job running. Any of them would also need a second deployment of the image, while the dispatch approach reuses the GitHub runner.

**Credentials:** cron-job.org holds one fine-grained GitHub token with **Actions: read and write** on this repository only (90-day expiry). It cannot read secrets or code. OpenAI and Gist credentials stay in GitHub secrets.

**Evidence:** the fixed public Gist remains the anonymous evidence. Match its `run_id`, `finished_at` and `git_sha` with the Actions run (named by trigger) and the uploaded artifact. A publisher failure fails the job; the previous public JSON can remain stale.

**Known limits:** a dispatch run reports `event=workflow_dispatch` and the token owner as actor, so the trigger is identified by the run name and the cron-job.org history, not by the event type. Token expiry must be renewed. Public-repository schedules are disabled after 60 days without activity; the external trigger is not.
