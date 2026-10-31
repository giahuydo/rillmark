# Rillmark

Scrapes public Zendesk help articles to clean Markdown and syncs only new or changed files to an OpenAI Vector Store. Built for a Playground support assistant.

- **Run artifact:** [public `last_run.json`](https://gist.githubusercontent.com/giahuydo/4968a3eec9704d752fbacb239964ee21/raw/last_run.json) ([history](https://gist.github.com/giahuydo/4968a3eec9704d752fbacb239964ee21)). It currently holds the latest **manual** live sync: 37 files skipped on re-run after 37 uploads. Scheduled runs will overwrite it once the scheduler is enabled.
- **Assistant screenshot:** pending a Playground check.

## Setup and run

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.sample .env              # set API_KEY (OpenAI project key)

python main.py --dry-run         # fetch + convert to out/*.md; no OpenAI calls, no key
python main.py --limit 3         # pilot: uploads at most 3 files, never detaches or deletes
python main.py                   # full sync; writes last_run.json; exit 0 only on full success
pytest                           # offline tests

docker build -t rillmark .
docker run -e API_KEY=sk-... rillmark main.py
```

Without `VECTOR_STORE_ID`, the job looks for the store tagged `managed_by=rillmark-optibot-v1` in the key's project: none → create, one → reuse, several → fail. The selection (3 sections, 37 articles, incl. the YouTube article) is in `config/selection.json`.

## How it works

- **Markdown:** one file per article: `# Title`, one `Article URL: <link>` line, then the body. Headings, code, tables, links (incl. relative), and images are kept; scripts and nav are removed.
- **Chunking:** static 4096 tokens, no overlap. The largest file is 2,725 `o200k_base` tokens, so one chunk per file (with its URL line) is expected but not yet confirmed by the provider. The run logs completed files and an estimated chunk count with its basis; `chunks.actual` stays `null`.
- **Delta sync:** SHA-256 of the Markdown plus schema and chunk settings, stored as a file attribute. Files are classified added / updated / skipped. A replacement is uploaded and confirmed complete before the old attachment is detached; no global file deletes. Articles removed at the source are reported, not deleted.
- **Report:** each run writes `last_run.json`. Non-dry runs with both `ARTIFACT_GIST_ID` and `ARTIFACT_GITHUB_TOKEN` also publish it to a gist; if publishing fails, the run exits non-zero.

## Daily cloud job

[GitHub Actions](https://github.com/giahuydo/rillmark/actions/workflows/rillmark-daily.yml) builds and runs the Docker image daily at `03:00 UTC` (10:00 Vietnam). After publishing the reviewed workflow on the default branch, configure secrets `OPENAI_API_KEY`, `ARTIFACT_GITHUB_TOKEN` and variable `ARTIFACT_GIST_ID`; `VECTOR_STORE_ID` is optional. Enable `RILLMARK_SCHEDULE_ENABLED=true` only after recurring cost approval. Actions → Run workflow defaults to `dry-run` (no upload or publishing); explicit `sync` requires approval and publishes to the public Gist. Reports are also retained as Actions artifacts, including failures when available. See [operations](docs/04-operations.md#3-scheduling-github-actions).

Scheduled execution is **PENDING**. The Gist currently contains manual evidence; confirm its `run_id`, timestamps and `git_sha` against a real scheduled run before claiming cloud freshness. Schedules may be delayed or disabled after inactivity. Open: Playground screenshot. Cut: oversize splitting and source-removal deletion.
