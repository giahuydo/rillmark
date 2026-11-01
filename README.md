# Rillmark

**Part 1:** scrapes Zendesk articles to Markdown and delta-syncs an OpenAI Vector Store for a Playground support assistant.

**Part 2:** [SCIO slice plan, Brief B](#part-2-scio-slice-plan-brief-b) (Team, Roles, Permissions, Assets and Screens).

- **Run artifact:** [public `last_run.json`](https://gist.githubusercontent.com/giahuydo/4968a3eec9704d752fbacb239964ee21/raw/last_run.json) shows the latest published run; compare `run_id` with Actions logs for freshness.
- **Assistant evidence:** Playground screenshot below shows the required YouTube answer and uploaded-file citation; the first reply does not print the full `Article URL:` line.

## Setup

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.sample .env
```

Set `API_KEY` (OpenAI project key) in `.env` for uploads; dry-run needs no key.

## How to run locally

```bash
python main.py --dry-run          # scrape to out/*.md; no OpenAI calls
python main.py --limit 3          # 3-file upload pilot; API_KEY required
python main.py                    # full delta sync; API_KEY required
pytest                            # offline tests

docker build -t rillmark .
docker run --env-file .env rillmark main.py  # one-shot Docker sync
```

Without `VECTOR_STORE_ID`, a `managed_by=rillmark-optibot-v1` store is created or reused by marker (ambiguity fails closed). `config/selection.json` selects 37 articles including YouTube.

## How it works

- **Markdown:** one file per article with title and `Article URL:` header; preserves headings, code, tables, links and images.
- **Chunking:** 4096 tokens, no overlap. Largest file: 2,725 `o200k_base` tokens. One chunk/file is expected, not provider-confirmed; logs distinguish completed files and estimated chunks, with `chunks.actual=null`.
- **Delta sync:** hashes Markdown plus schema/chunk settings; classifies added, updated and skipped. Replacement completes before old attachment detaches. Source removals are reported, not deleted.
- **Report:** each run writes `last_run.json`. Configured non-dry runs publish to the fixed Gist; publication failure exits non-zero.

## Beyond Assignment Requirements

**Run history:** beyond the required last-run artifact, the [same Gist](https://gist.github.com/giahuydo/4968a3eec9704d752fbacb239964ee21) keeps `history.json` with the latest **30 distinct runs** (three cloud sync runs so far, each `added=0 updated=0 skipped=37`; [delta evidence](docs/05-testing.md#31-delta-sync-evidence)). GitHub Actions keeps the full logs.

**Separate optional demo:** [StrangeLoop agent workflow and six screenshots](docs/engineering-decisions-and-alternatives.md#3-beyond-scope-independently-developed-agent-workflow). This is additional engineering evidence, not a substitute for the required OpenAI workflow.

## Daily cloud job

**Every day at 03:23 UTC, [cron-job.org](https://cron-job.org) dispatches the [GitHub Actions workflow](https://github.com/giahuydo/rillmark/actions/workflows/rillmark-daily.yml)** in `sync` mode; runs are named `Rillmark daily (cron-job.org)`. GitHub's own cron (`47 3 * * *`) is a standby, switched off with `RILLMARK_SCHEDULE_ENABLED=false` so the job runs once a day. Why an external trigger: GitHub's schedule arrived 7 hours late in our test while cron-job.org fired on time, and it is free where Render and similar cron services are paid ([ADR-0004](docs/adr/0004-scheduler.md), [evidence](docs/04-operations.md#scheduler-evidence-1-nov-2026)). Each run's `run_id` and `git_sha` match the public Gist. Cut: oversize splitting, source-removal deletion.

## Playground screenshot

![OptiBot answering the YouTube question using File Search, with a citation to the uploaded Markdown article](docs/screenshots/openai/optibot-youtube-playground.png)

For architecture, design decisions, testing, and detailed operations, see the [Engineering documentation](docs/README.md).

## Part 2: SCIO slice plan (Brief B)

**Chosen brief: B** (Team, Roles, Permissions, uploaded Assets and Screens): what to build, in what order, how long, and why. Start at [`docs/part2/README.md`](docs/part2/README.md) (Markdown + Mermaid on GitHub). To view it as a Starlight site (Node 22): `cd site && npm install && npm run dev`, then open http://localhost:4600.
