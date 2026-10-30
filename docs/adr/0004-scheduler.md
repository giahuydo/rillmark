# ADR-0004 — Scheduler: Render Cron Job + Public `last_run.json`

Back to [docs index](../README.md). Related: [04-operations](../04-operations.md#3-scheduling-render-cron-job), [02 §5](../02-data-contracts.md#5-last_runjson-public-artifact).

- **Status:** Accepted for Render and public GitHub Gist publisher method. G5 URL, cost and live proof remain UNKNOWN.

## 1. Context

R11 asks to schedule the Docker job once a day on "DigitalOcean or any cloud/public hosting platform (e.g. Railway, Render, Fly.io, AWS, GCP)". R13 asks for "a link to job logs or last run artefact" that a reviewer can open.

## 2. Decision

- **Render Cron Job**, runtime Docker, built from the GitHub repo, schedule `0 3 * * *` UTC.
- **G5 public publisher method APPROVED by the project author: public GitHub Gist.** Update a fixed public `last_run.json` gist using a **gist-scope-only token**, never a broader repo-write credential. Render logs may require dashboard access (ASSUMPTION), so a screenshot is supplementary, not a live link. The exact anonymous raw URL, Render/Gist cost and fresh live proof stay **UNKNOWN** until implementation; approval of the method alone does not close G5 ([04 §4](../04-operations.md#4-logs-and-public-run-artifact)).
- Scheduled runs require publication. A local/evaluator invocation with only `API_KEY` and no publisher credentials may skip it; this does not establish the scheduled public-link gate. Other publisher backends require separate owner approval if Gist implementation fails.
- Publisher uses a schema-field allowlist and redacted `errors[]`; no secret, PII, raw Zendesk body, or exception text enters the public artifact. Attempt publication of safe partial/failed sync results without relabeling them success. Exit **0 only when sync and required publish both succeed**. Sync partial/failed → **1**; sync ok but publish failed/unsafe → **1** with `publish_failed` logged to Render/local logs and a safe local error where possible. A stale public URL cannot disclose this failure and must never claim to show the latest attempt. Validate the Gist raw URL anonymously (200, safe JSON, matching the scheduled run's `run_id`/timestamp/status) and exercise partial/failure cases.

## 3. Alternatives considered

| Option | Why not chosen |
|---|---|
| GitHub Actions `schedule` | Logs are public and it is free, but it is a CI system. It is not clearly one of the "hosting platforms" the assignment names, and that area is worth 15 pts. Fallback only. |
| Railway / Fly.io cron | Equivalent. Render is named in the assignment and has a native Cron Job service type. |
| DigitalOcean App Platform job / Droplet + crontab | A Droplet needs host management. App Platform is equivalent but has no advantage here. |
| Always-on container with an in-process scheduler | Violates "runs once and exits", and costs more. |

## 4. Consequences

- **Cost:** Render Cron Jobs are billed per run-minute (ASSUMPTION, check pricing before P4). Expected about 1 minute a day.
- **Single command policy:** image exec-form `ENTRYPOINT ["python"]` + `CMD ["main.py"]`; Docker's documented exec-form argv semantics are `docker run <image>` and `docker run <image> main.py` → `python main.py` (not yet exercised with this project image). Render custom command stays **unset** to inherit the image default; Render's actual mapping of unset command to Docker argv remains UNKNOWN. In P4 check its docs/UI and no-upload runtime argv/exit. Only if Render requires a CMD-argument replacement and this is confirmed, enter `main.py` and verify. Never enter `python main.py` as a CMD replacement; stop if Render overrides ENTRYPOINT or behaves differently ([04 §3](../04-operations.md#3-scheduling-render-cron-job)).
- **Startup/store policy:** primary planned command `docker run -e API_KEY=... <image> main.py` uses versioned non-secret `config/selection.json` (`section_ids` = `[26324076807315, 26324141467539, 26324224269459]`, `youtube_article_id` = `360051014713`, `min_articles` = 30), with optional `SECTION_IDS`/`YOUTUBE_ARTICLE_ID` overrides. Sync validates the full selection, then resolves the store in the key's project. `VECTOR_STORE_ID` set → retrieve it, require vector store `metadata.managed_by = "rillmark-optibot-v1"`, else fail closed. Unset → list stores in the key's project (all pages), filter by the marker: 0 → create named `rillmark-optibot` with marker and no `expires_after`; 1 → reuse; >1 → fail closed. Display name is never used for matching; file-attribute marker remains `managed_by = "rillmark-optibot-v1"`. `--init-store` is removed. A grader's different-project key creates its own marked store; no author's store ID is hardcoded. Primary command remains **UNVERIFIED until G0 + P4** ([04 §2](../04-operations.md#2-docker-contract)).
- **Secrets:** the project API key and approved public-Gist gist-scope-only credential live in Render environment variables; local Python loads `.env` with `python-dotenv` (exported values take precedence), and Docker configured runs use `--env-file`. Never publish credentials or PII.
- **Gate (P4/G5):** after G0, verify primary one-flag Docker command in a fresh authorized project and repeat reuse, then one *scheduled* (not manual) run and an anonymous public-Gist link to the same `run_id`. Method approval is not live proof: both primary CLI and G5 URL/freshness remain unverified until exercised. Before the first commit, remove internal tracking IDs, tooling/assistant names and private notes from public-facing root README/published docs; license/ToS for fixtures/raw support content is **UNKNOWN** and must be checked before publication. Commit/push only after the project author approves first-commit contents.
