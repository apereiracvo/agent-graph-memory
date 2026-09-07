# Working in this repo

**Agent Graph Memory (AGM)** is an experimental project-memory repository built on
[Graphiti](https://github.com/getzep/graphiti) and [FalkorDB](https://www.falkordb.com/), with an
active Cognee comparison/benchmark effort under `cognee_bench/`. The repository embeds the published
`graphiti-core` package in small Python commands, runs FalkorDB in Docker, and exposes the same graph
to OpenCode through the Graphiti MCP server. This file is the canonical governance map for software
and agent work done here; the root `README.md` is the operational lifecycle reference.

## What this repo is

- **Experimental.** Claims in docs, reports, and reviews must distinguish observed, verified reality
  from design intent or speculation.
- **Dual-path.** The production-facing path is `src/agent_graph_memory/` (+ Graphiti/FalkorDB/MCP).
  The active research path is `cognee_bench/`, driven by a separate Cognee session. Keep these
  surfaces distinct: no cross-path coupling, and no writes to an active Cognee session's state.
- **Runtime local.** Graphs, episodes, and benchmark state are disposable local artifacts, not
  application data sources of record.

## Authoritative read order

1. `AGENTS.md` (this file) — governance, ownership, and safety.
2. `README.md` — lifecycle, MCP, and configuration (`.env.local`, models, Docker profiles).
3. `docs/` — analysis and decisions (`graphiti-scaling.md`, `falkordb-vs-neo4j.md`,
   `graphiti-growth-forecast.md`, `falkordb-performance.md`, `company-product-agent-protocol.md`).
4. Targeted source under `src/agent_graph_memory/`, tests under `tests/`, and `cognee_bench/`
   documentation before changing that path.

## App structure and commands

- Python package: `src/agent_graph_memory/`; CLI entrypoints via `pyproject.toml` (`[project.scripts]`).
- Tests: `tests/` for the main package; `cognee_bench/tests/` only for Cognee-scoped work.
- Runtime: `docker compose` services `falkordb`, `tools`, and the `mcp` profile.
- Verification / validation commands (do not invent others):
  - `uv run pytest tests` — main path (Graphiti/FalkorDB) tests only.
  - `uv run ruff check src tests` — main path lint scope.
  - `docker compose config`
- Main-path commands intentionally exclude `cognee_bench/`: it is not part of the `uv` project.
  Run the Cognee lane only in its isolated venv (never through `uv run` or merged deps):
  `PYTHONPATH=. .venv-cognee/bin/python -m pytest cognee_bench/tests -q`
- Read a script, Dockerfile, or compose file before running it. Never run server-affecting,
  graph-deleting, or cost-incurring operations without an explicit task scope.

## Sensitive material — hard boundaries

The following are **never** read, printed, committed, or used as context, and must not be copied into
workbooks, reviews, or durable docs. This is an agent permission boundary, not just a Git ignore:

- `.env.local` and any other runtime-local env file (real API keys, org IDs, credentials).
- `.graphiti/` — extracted episode files (`.jsonl`) and local graph state.
- `cognee_bench/.state/` and any Cognee state/cache written by the parallel session.
- Credentials, tokens, private keys, raw HP (Hello Pediatrics) content, and personal data.
- Session-local generated bookmarks, workbooks outside `docs/temp/`, or other unattached runtime state.

`.env.example` is the only tracked environment template; real values belong only in ignored local files.

## Destructive operations require explicit confirmation

- **Graph clear/reset** via the MCP clear tools, `docker compose down -v`, or deleting `.graphiti/`
  episodes permanently removes memory. Never perform one without explicit human (or approved-task)
  confirmation naming the exact graph group.
- Prefer isolation: use a scoped `GRAPHITI_GROUP_ID`/`FALKORDB_DATABASE` (e.g. in benchmarks) and leave
  the shared `agent_graph_memory` graph untouched unless the task authorizes mutation.
- `docker compose --profile mcp down` stops MCP + FalkorDB but preserves graph data; only `-v`
  deletes the FalkorDB volume.
- Session and cost-aware tooling (LLM-backed ingest/benchmarks): confirm scope and model before running.

## Workbooks and temporary artifacts

- Multi-step agent work is tracked in workbooks under `docs/temp/<team>/<timestamp>-<source-id>/`,
  created with `ops-init-workbook`. Workbooks are execution artifacts, not durable documentation.
- Durable documentation belongs under `docs/` (analysis, decisions, performance, scaling); promote
  only verified, lean findings via `ops-promote-docs`. Do not wholesale-copy workbooks into `docs/`.
- Generated benchmark reports belong under `reports/` when they are intended deliverables; sanitize
  them before promotion.

## OpenCode / agent conventions

- `opencode.json` selects the project default model, routes through the `orchestrator` primary agent,
  and declares MCP servers (Graphiti memory, Playwright, Context7) and provider/auth plugins.
- Agent definitions live in `.opencode/agents/`; reusable skills in `.opencode/skills/`. Owned work
  is routed per the orchestrator's table. Formal reviews are read-only and never self-apply findings.
- The Graphiti MCP may mutate or clear memory; treat its tools as operational surfaces subject to the
  destructive-operation rule above. Restart OpenCode after starting the MCP profile so it reloads
  project configuration.