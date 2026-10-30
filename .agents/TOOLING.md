# Agent tooling

How each coding agent runtime loads this repository's rules, skills, and MCP servers, and what was verified. Rules themselves live only in [`AGENTS.md`](../AGENTS.md).

Verified 2026-10-31 with Claude Code 2.1.314, Codex CLI 0.162.1, Pi 1.4.0. Labels: **VERIFIED** (smoke-tested here), **DOCUMENTED** (runtime docs), **NOT_AVAILABLE**, **DEFERRED**.

## Layout

| Path | Purpose |
|---|---|
| `AGENTS.md` | Single source of rules for every agent |
| `CLAUDE.md` | Claude Code adapter: imports `@AGENTS.md` |
| `.agents/skills/<name>/SKILL.md` | Shared skills: `commit`, `python-standards`, `implement-task` |
| `.claude/skills` | Symlink → `../.agents/skills` (Claude Code's project skill path) |
| `.mcp.json` | Claude Code project MCP servers (`context7`) |
| `.pi/mcp.json` | Pi project MCP servers (`context7`) |

No secrets or machine-specific paths are stored in these files. MCP servers run through `npx` and need no API key.

## Matrix

| Capability | Claude Code | Codex CLI | Pi |
|---|---|---|---|
| Reads `AGENTS.md` rules | **VERIFIED** via `CLAUDE.md` import | **VERIFIED** (native) | **VERIFIED** (native, loads without project trust) |
| Discovers `.agents/skills` | **VERIFIED** via `.claude/skills` symlink | **VERIFIED** (native) | **VERIFIED** only with project trust (`--approve` or saved trust); skipped otherwise |
| Context7 MCP (library docs) | Configured in `.mcp.json`; approve the project server on first use | Uses the user-level `context7` server if configured | **NOT_AVAILABLE** when started with `--no-extensions` (MCP is a built-in extension); needs project trust otherwise |
| Context7 server itself | **VERIFIED**: `@upstash/context7-mcp` v4.4.4 started over stdio, listed `resolve-library-id`/`query-docs`, resolved `/openai/openai-python` | same server | same server |
| CodeGraph | **DEFERRED** until code exists (index after the first code commit) | **DEFERRED** | **DEFERRED** |
| Serena (symbol navigation) | **DEFERRED** until code exists | **DEFERRED** | **DEFERRED** |
| Git | CLI only (integrator) | CLI only | CLI only |

Smoke prompt used for every runtime (no tools allowed): "the Python version this repository requires, the project skill names you can see, which role may run git commit". Claude Code and Codex answered `Python 3.12`, all three skills, `Integrator`. Pi answered `Python 3.12` and `Integrator`, and listed the three skills only when project trust was granted.

## Setup notes

- **Claude Code:** on the first interactive run in this repo, approve the `context7` project MCP server when prompted.
- **Codex:** reads `AGENTS.md` and `.agents/skills` without extra setup. Context7 comes from the user's own Codex MCP configuration; no project config is added, to avoid duplicating it.
- **Pi:** trust this project once (start `pi` here and approve, or `/trust`) so non-interactive runs load `.agents/skills` and `.pi/mcp.json`. Until then, task cards tell Pi to read the needed `SKILL.md` files explicitly, and library-doc lookups are done by an agent with Context7, then pasted into the task card.
- **CodeGraph / Serena:** after the first Python code commit, index the repo and add them here with their own smoke results.
