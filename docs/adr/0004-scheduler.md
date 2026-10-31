# ADR-0004 — Scheduler: GitHub Actions + public Gist

Status: Accepted. Supersedes the earlier Render Cron decision.

The daily job uses `.github/workflows/rillmark-daily.yml` on GitHub-hosted Ubuntu: build the existing Dockerfile, run its non-root application once, preserve its exit code, and copy the report even after failure. No registry or Render service is required.

Schedule: `0 3 * * *` UTC (10:00 Vietnam), gated by repository variable `RILLMARK_SCHEDULE_ENABLED=true` after credentials and recurring cost approval. Manual dispatch defaults to `dry-run`; explicit `sync` requires OpenAI and Gist configuration and `REQUIRE_PUBLISH=true`.

The fixed public Gist remains the anonymous evidence mechanism. Match its timestamp-based `run_id`, `finished_at` and `git_sha` with the corresponding Actions log and uploaded artifact. Existing manual evidence does not verify scheduled execution. A publisher failure must fail the job; the previous public JSON can remain stale.

Actions schedules can be delayed/dropped or disabled after public-repository inactivity. Artifact collection is best effort on cancellation or runner loss. See [operations](../04-operations.md#3-scheduling-github-actions) for setup and verification. A real scheduled run remains PENDING; no paid call or schedule activation is authorized by this configuration change.
