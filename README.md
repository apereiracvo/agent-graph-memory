# Agent Graph Memory

Experimental project memory using [Graphiti](https://github.com/getzep/graphiti),
[FalkorDB](https://www.falkordb.com/), and Graphiti's experimental MCP server.

Graphiti is a Python library, not a database or a REST service. This repository embeds the
published `graphiti-core` package in small Python commands, runs FalkorDB in Docker, and exposes
the same graph to OpenCode through the official Graphiti MCP container.

## Prerequisites

- Docker with Compose
- An OpenAI API key (Graphiti uses an LLM, embeddings, and reranking)
- Optional: Python 3.12 and [uv](https://docs.astral.sh/uv/) for running commands outside Docker

## Lifecycle

The intended workflow is:

1. Start FalkorDB.
2. Run as many independent insert and query commands as needed.
3. Stop the containers when finished.

The database container is long-lived during a work session. The Python tools are short-lived
processes that connect to it, do one job, and exit.

### 1. Start The Database

```bash
cp .env.example .env.local
# Set OPENAI_API_KEY in .env.local
docker compose up -d falkordb
```

Services:

- FalkorDB: `localhost:6379`
- FalkorDB browser: <http://localhost:3000>

### 2. Insert And Query

Extraction is local and makes no API calls. It reads Git-visible text files and writes episodes
to ignored `.graphiti/episodes.jsonl`, allowing review before LLM-backed ingestion.

Run entirely through Docker:

```bash
docker compose run --rm tools extract .
docker compose run --rm tools ingest --limit 3
docker compose run --rm tools query "What technologies does this project use?"
```

Repeat `ingest` and `query` as often as needed. `docker compose run --rm` creates a temporary tool
container for each command while the FalkorDB container and its graph remain available.

Remove `--limit 3` after the initial smoke test. Each file is processed sequentially because
Graphiti uses recent episodes as context and recommends sequential episode ingestion.

Run with local Python instead:

```bash
uv sync --extra dev
uv run graph-memory extract .
uv run graph-memory ingest --limit 3
uv run graph-memory query "How is project memory stored?"
```

To extract another repository while using Docker, mount it into the tools container:

```bash
docker compose run --rm -v /absolute/project:/target tools \
  extract /target --output /workspace/.graphiti/target.jsonl
```

### 3. Stop The Containers

```bash
docker compose down
```

FalkorDB data remains in the `falkordb-data` Docker volume and is available the next time the
database starts. To intentionally delete the graph as well as the containers, run:

```bash
docker compose down -v
```

## OpenCode MCP

The project-local `opencode.json` points OpenCode at the optional HTTP MCP server. When MCP access
is needed, start it and FalkorDB together:

```bash
docker compose --profile mcp up -d
```

The MCP endpoint is <http://localhost:8100/mcp> and its liveness endpoint is
<http://localhost:8100/health>. Quit and restart OpenCode after starting it so OpenCode reloads the
project configuration. The MCP tools can add memories, search entities and facts, inspect
episodes, and clear the graph. `docker compose --profile mcp down` stops both MCP and FalkorDB
without deleting graph data.

Both the scripts and MCP use `GRAPHITI_GROUP_ID=agent_graph_memory`. With FalkorDB, Graphiti maps
that group to a physical FalkorDB graph, so changing the value creates/selects another isolated
memory graph. Keep `FALKORDB_DATABASE` equal to it to avoid surprising behavior in MCP operations.

## Configuration Notes

- `graphiti-core` is pinned in `pyproject.toml`; no Graphiti source checkout or fork is required.
- `httpx` is declared directly because the `graphiti-core==0.29.3` wheel currently imports it but
  declares the separate `httpx2` distribution.
- The MCP image is built directly from pinned official Graphiti commit `993e081`. The build uses
  `graphiti-core==0.29.3`, avoiding the older core bundled in the published standalone image without
  cloning or vendoring Graphiti into this repository.
- `falkordb/falkordb:latest` follows Graphiti's official local setup. Pin it before relying on this
  experiment for repeatable or production workloads.
- Runtime secrets and local settings live in ignored `.env.local`; `.env.example` is the template.
- The current scripts use Graphiti's default OpenAI clients. Provider-specific configuration can
  be added when the experiment needs Anthropic, Gemini, Azure OpenAI, or a local compatible model.
- Graphiti has no built-in REST API. If non-MCP HTTP access is needed, add a small application API
  around `graphiti-core` rather than depending on the older separately published server image.

### Models

Configure the current OpenAI setup in `.env.local`:

```dotenv
# Entity and fact extraction
MODEL_NAME=gpt-5.6-luna

# Entity and fact embeddings (1536 dimensions in config/graphiti-mcp.yaml)
EMBEDDER_MODEL=text-embedding-3-small
```

The MCP server does not currently expose an independent reranker model setting. With OpenAI as the
LLM provider, Graphiti selects its OpenAI reranker and currently uses `gpt-4.1-nano` internally.
Changing `MODEL_NAME` does not change that reranker model. Provider selection and embedding
dimensions are configured in `config/graphiti-mcp.yaml`.

## Development

```bash
uv run pytest
uv run ruff check .
docker compose config
```

Official references: [Graphiti repository](https://github.com/getzep/graphiti),
[Graphiti PyPI package](https://pypi.org/project/graphiti-core/), and
[Graphiti MCP server](https://github.com/getzep/graphiti/tree/main/mcp_server).
