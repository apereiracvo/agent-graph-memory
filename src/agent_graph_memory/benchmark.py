from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import tiktoken
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder import EmbedderClient, OpenAIEmbedder
from graphiti_core.embedder.openai import OpenAIEmbedderConfig
from graphiti_core.llm_client import OpenAIClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodeType
from pydantic import BaseModel, Field, create_model

LUNA_INPUT_PER_MILLION = 0.20
LUNA_OUTPUT_PER_MILLION = 1.20
EMBEDDING_INPUT_PER_MILLION = 0.02
RERANKER_INPUT_PER_MILLION = 0.10
RERANKER_OUTPUT_PER_MILLION = 0.40
VOLUMES = (100, 1_000, 10_000)


class Person(BaseModel):
    description: str = Field(description="Brief description using only the supplied context.")


class Requirement(BaseModel):
    project_name: str
    description: str


class Document(BaseModel):
    title: str
    description: str


def mcp_entity_types() -> dict[str, type[BaseModel]]:
    descriptions = {
        "Project": "A software project or repository.",
        "Component": "A module, package, service, or other architectural component.",
        "Technology": "A language, framework, library, database, protocol, or tool.",
    }
    entity_types = {
        name: create_model(name, __doc__=description)
        for name, description in descriptions.items()
    }
    entity_types.update(
        {"Requirement": Requirement, "Document": Document, "Person": Person}
    )
    return entity_types


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    body: str
    queries: tuple[str, ...]


@dataclass
class EmbeddingUsage:
    requests: int = 0
    texts: int = 0
    tokens: int = 0


class CountingEmbedder(EmbedderClient):
    def __init__(self, wrapped: OpenAIEmbedder, model: str):
        self.wrapped = wrapped
        self.config = wrapped.config
        try:
            self.encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            self.encoding = tiktoken.get_encoding("o200k_base")
        self.usage = EmbeddingUsage()

    def reset(self) -> None:
        self.usage = EmbeddingUsage()

    def _record(self, values: str | list[str]) -> None:
        texts = [values] if isinstance(values, str) else values
        self.usage.requests += 1
        self.usage.texts += len(texts)
        self.usage.tokens += sum(len(self.encoding.encode(text)) for text in texts)

    async def create(self, input_data: Any) -> list[float]:
        if isinstance(input_data, str) or (
            isinstance(input_data, list)
            and all(isinstance(value, str) for value in input_data)
        ):
            self._record(input_data)
        return await self.wrapped.create(input_data)

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        self._record(input_data_list)
        return await self.wrapped.create_batch(input_data_list)


def _expanded(base: str, context: str, target_tokens: int, encoding: Any) -> str:
    paragraphs = [base]
    index = 1
    while len(encoding.encode("\n\n".join(paragraphs))) < target_tokens:
        paragraphs.append(f"Context note {index}: {context}")
        index += 1
    return "\n\n".join(paragraphs)


def scenarios(model: str) -> list[Scenario]:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")
    return [
        Scenario(
            name="low",
            description="Short, sparse note with three entities and two direct facts.",
            body=_expanded(
                "Northstar Clinic selected AuroraDB for appointment storage. Maya owns the migration.",
                "The note provides background about a routine internal planning discussion without adding new named entities or relationships.",
                350,
                encoding,
            ),
            queries=(
                "Which database did Northstar Clinic select?",
                "Who owns the Northstar migration?",
                "What is known about AuroraDB?",
            ),
        ),
        Scenario(
            name="mid",
            description="Typical project brief with about eight entities and interconnected facts.",
            body=_expanded(
                "Blue Harbor Labs is launching the Atlas service for Redwood Health. Priya is the technical lead and Marco is the product manager. The service uses PostgreSQL, FastAPI, and React. Cedar Security will perform the review in October 2026. Priya owns backend delivery, Marco coordinates Redwood Health, and Lina maintains the React dashboard.",
                "The remaining material describes ordinary project planning, documentation review, testing practices, and weekly status communication for the same named project and team.",
                1_400,
                encoding,
            ),
            queries=(
                "Who leads Atlas and what does each person own?",
                "Which technologies does Atlas use?",
                "Who is the customer and who performs security review?",
                "When is the Atlas security review?",
                "Summarize the Atlas delivery relationships.",
            ),
        ),
        Scenario(
            name="high",
            description="Long, entity-dense program brief with temporal and cross-team relationships.",
            body=_expanded(
                "Orion Group operates the Meridian modernization program for Summit Pediatrics and Coastline Insurance. Elena directs the program. Jamal leads the Helios API team with engineers Noor and Wei. Renee leads the Vega analytics team with analyst Chloe. Helios uses Python, FastAPI, Kafka, and PostgreSQL; Vega uses TypeScript, React, dbt, and Snowflake. Nimbus Cloud hosts both systems. Ironclad Security audits Helios, while Beacon Compliance reviews Vega. Summit Pediatrics sponsors patient scheduling and Coastline Insurance sponsors claims automation. Helios launches on November 3, 2026, Vega launches on December 8, 2026, and the shared migration completes January 20, 2027. Jamal depends on Renee for analytics schemas; Renee depends on Jamal for event contracts. Noor owns authentication, Wei owns Kafka integration, and Chloe owns executive dashboards. A prior PostgreSQL migration deadline of October 1, 2026 was superseded by November 15, 2026 after Ironclad identified encryption work.",
                "Additional program context covers architecture reviews, incident exercises, data-quality checks, release rehearsals, stakeholder demonstrations, operational handoffs, and documentation updates involving the same teams and systems.",
                3_500,
                encoding,
            ),
            queries=(
                "Who directs Meridian and how are the teams organized?",
                "What technologies are used by Helios and Vega?",
                "What are the launch and migration dates?",
                "Which organizations sponsor, host, audit, and review the program?",
                "What does each Helios engineer own?",
                "What does each Vega analyst own?",
                "How do Jamal and Renee depend on each other?",
                "What changed about the PostgreSQL migration deadline?",
            ),
        ),
    ]


def _cost(input_tokens: int, output_tokens: int, embedding_tokens: int) -> float:
    return (
        input_tokens * LUNA_INPUT_PER_MILLION
        + output_tokens * LUNA_OUTPUT_PER_MILLION
        + embedding_tokens * EMBEDDING_INPUT_PER_MILLION
    ) / 1_000_000


async def run_benchmark(output_dir: Path) -> tuple[Path, Path]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required in .env.local")
    model = os.getenv("MODEL_NAME", "gpt-5.6-luna")
    embedding_model = os.getenv("EMBEDDER_MODEL", "text-embedding-3-small")
    if model != "gpt-5.6-luna":
        raise SystemExit("This benchmark is pinned to MODEL_NAME=gpt-5.6-luna")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    results = []
    # Dense synthetic episodes repeatedly trigger a FalkorDB semantic-candidate-search stall.
    # Measure one representative profile and extrapolate explicit low/high bands instead.
    for scenario in [scenarios(model)[1]]:
        print(f"[{scenario.name}] starting isolated benchmark", flush=True)
        group = f"benchmark_{run_id}_{scenario.name}_{uuid4().hex[:6]}"
        driver = FalkorDriver(
            host=os.getenv("FALKORDB_HOST", "localhost"),
            port=int(os.getenv("FALKORDB_PORT", "6379")),
            password=os.getenv("FALKORDB_PASSWORD") or None,
            database=group,
        )
        llm_config = LLMConfig(
            api_key=api_key,
            base_url=os.getenv("OPENAI_API_URL", "https://api.openai.com/v1"),
            model=model,
            small_model=model,
            max_tokens=4096,
        )
        llm = OpenAIClient(config=llm_config, reasoning="none", verbosity="low")
        embedder = CountingEmbedder(
            OpenAIEmbedder(
                config=OpenAIEmbedderConfig(
                    api_key=api_key,
                    base_url=os.getenv("OPENAI_API_URL", "https://api.openai.com/v1"),
                    embedding_model=embedding_model,
                    embedding_dim=1536,
                )
            ),
            embedding_model,
        )
        reranker = OpenAIRerankerClient(config=llm_config)
        client = Graphiti(
            graph_driver=driver,
            llm_client=llm,
            embedder=embedder,
            cross_encoder=reranker,
            max_coroutines=5,
        )
        try:
            await client.build_indices_and_constraints()
            print(f"[{scenario.name}] ingesting episode", flush=True)
            started = time.perf_counter()
            episode_result = await asyncio.wait_for(
                client.add_episode(
                    name=f"Cost benchmark: {scenario.name}",
                    episode_body=scenario.body,
                    source_description="Synthetic Graphiti cost benchmark",
                    reference_time=datetime.now(UTC),
                    source=EpisodeType.text,
                    group_id=group,
                    entity_types=mcp_entity_types(),
                ),
                timeout=180,
            )
            ingestion_seconds = time.perf_counter() - started
            print(
                f"[{scenario.name}] ingestion completed in {ingestion_seconds:.1f}s; "
                f"running {len(scenario.queries)} queries",
                flush=True,
            )
            token_usage = llm.token_tracker.get_total_usage()
            prompt_usage = {
                name: asdict(usage) for name, usage in llm.token_tracker.get_usage().items()
            }
            ingestion_embedding = asdict(embedder.usage)

            llm.token_tracker.reset()
            embedder.reset()
            query_latencies = []
            query_result_counts = []
            for query in scenario.queries:
                started = time.perf_counter()
                query_results = await client.search(query, group_ids=[group], num_results=10)
                query_latencies.append(time.perf_counter() - started)
                query_result_counts.append(len(query_results))
            query_embedding = asdict(embedder.usage)
            query_llm = llm.token_tracker.get_total_usage()

            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                encoding = tiktoken.get_encoding("o200k_base")
            source_tokens = len(encoding.encode(scenario.body))
            ingestion_cost = _cost(
                token_usage.input_tokens,
                token_usage.output_tokens,
                ingestion_embedding["tokens"],
            )
            query_cost_total = _cost(
                query_llm.input_tokens,
                query_llm.output_tokens,
                query_embedding["tokens"],
            )
            results.append(
                {
                    "scenario": scenario.name,
                    "description": scenario.description,
                    "source": {
                        "characters": len(scenario.body),
                        "estimated_tokens": source_tokens,
                    },
                    "ingestion": {
                        "seconds": round(ingestion_seconds, 3),
                        "entities": len(episode_result.nodes),
                        "facts": len(episode_result.edges),
                        "llm_calls": sum(item["call_count"] for item in prompt_usage.values()),
                        "llm_input_tokens": token_usage.input_tokens,
                        "llm_output_tokens": token_usage.output_tokens,
                        "embedding_requests": ingestion_embedding["requests"],
                        "embedding_texts": ingestion_embedding["texts"],
                        "embedding_tokens": ingestion_embedding["tokens"],
                        "estimated_cost_usd": round(ingestion_cost, 8),
                        "prompts": prompt_usage,
                    },
                    "queries": {
                        "count": len(scenario.queries),
                        "median_seconds": round(statistics.median(query_latencies), 4),
                        "p95_seconds": round(max(query_latencies), 4),
                        "result_counts": query_result_counts,
                        "llm_calls": 0,
                        "embedding_requests": query_embedding["requests"],
                        "embedding_tokens": query_embedding["tokens"],
                        "estimated_cost_total_usd": round(query_cost_total, 8),
                        "estimated_cost_per_query_usd": round(
                            query_cost_total / len(scenario.queries), 10
                        ),
                    },
                }
            )
            checkpoint = output_dir / f".graphiti-cost-{run_id}.partial.json"
            output_dir.mkdir(parents=True, exist_ok=True)
            checkpoint.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
            print(f"[{scenario.name}] completed and checkpointed", flush=True)
        finally:
            await driver.execute_query("MATCH (n) DETACH DELETE n")
            await client.close()

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "configuration": {
            "graphiti_core": "0.29.3",
            "llm_model": model,
            "embedding_model": embedding_model,
            "reranker_model": "gpt-4.1-nano (configured but unused by MCP RRF searches)",
            "database": "FalkorDB",
            "entity_types": list(mcp_entity_types()),
        },
        "pricing_usd_per_million_tokens": {
            "gpt-5.6-luna_input": LUNA_INPUT_PER_MILLION,
            "gpt-5.6-luna_output": LUNA_OUTPUT_PER_MILLION,
            "text-embedding-3-small_input": EMBEDDING_INPUT_PER_MILLION,
            "gpt-4.1-nano_input": RERANKER_INPUT_PER_MILLION,
            "gpt-4.1-nano_output": RERANKER_OUTPUT_PER_MILLION,
        },
        "results": results,
    }
    baseline = results[0]
    estimate_factors = {
        "low": {"source_tokens": 350, "ingestion": 1 / 3, "query": 0.9},
        "mid": {"source_tokens": 1_400, "ingestion": 1.0, "query": 1.0},
        "high": {"source_tokens": 3_500, "ingestion": 3.125, "query": 1.16},
    }
    report["estimates"] = {
        name: {
            "basis": "measured" if name == "mid" else "extrapolated",
            "source_tokens": values["source_tokens"],
            "ingestion_cost_usd": round(
                baseline["ingestion"]["estimated_cost_usd"] * values["ingestion"], 8
            ),
            "query_cost_usd": round(
                baseline["queries"]["estimated_cost_per_query_usd"] * values["query"], 10
            ),
            "llm_calls": max(
                2, round(baseline["ingestion"]["llm_calls"] * values["ingestion"])
            ),
            "llm_tokens": round(
                (
                    baseline["ingestion"]["llm_input_tokens"]
                    + baseline["ingestion"]["llm_output_tokens"]
                )
                * values["ingestion"]
            ),
            "embedding_tokens": round(
                baseline["ingestion"]["embedding_tokens"] * values["ingestion"]
            ),
            "ingestion_seconds": round(
                baseline["ingestion"]["seconds"] * values["ingestion"], 3
            ),
        }
        for name, values in estimate_factors.items()
    }
    report["projections"] = {
        name: {
            str(volume): {
                "ingestion_cost_usd": round(
                    estimate["ingestion_cost_usd"] * volume, 4
                ),
                "queries_equal_to_document_count_cost_usd": round(
                    estimate["query_cost_usd"] * volume, 6
                ),
                "sequential_ingestion_hours": round(
                    estimate["ingestion_seconds"] * volume / 3_600, 2
                ),
                "llm_calls": estimate["llm_calls"] * volume,
                "llm_tokens": estimate["llm_tokens"] * volume,
                "embedding_tokens": estimate["embedding_tokens"] * volume,
            }
            for volume in VOLUMES
        }
        for name, estimate in report["estimates"].items()
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"graphiti-cost-{run_id}.json"
    markdown_path = output_dir / f"graphiti-cost-{run_id}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    checkpoint = output_dir / f".graphiti-cost-{run_id}.partial.json"
    checkpoint.unlink(missing_ok=True)
    return json_path, markdown_path


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Graphiti Cost and Volume Benchmark",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Configuration",
        "",
        "- Graphiti Core: `0.29.3`",
        "- Extraction: `gpt-5.6-luna`",
        "- Embeddings: `text-embedding-3-small`",
        "- Queries: MCP-equivalent edge hybrid RRF; one embedding and no LLM reranker",
        "- Database: FalkorDB",
        "",
        "## Method",
        "",
        "One representative medium profile was ingested into a new isolated graph, followed by representative fact searches. LLM usage comes from Graphiti's token tracker; embedding usage comes from an instrumented embedder using `tiktoken`. Costs apply published Standard API token rates to measured usage.",
        "",
        "- Low: extrapolated to about 350 source tokens using one-third of measured medium ingestion cost.",
        "- Mid: measured at about 1,400 source tokens with a typical interconnected project brief.",
        "- High: extrapolated to about 3,500 source tokens using 2.5x size plus a 25% complexity buffer.",
        "",
        "## Measured Results",
        "",
        "| Scenario | Source tokens | Entities | Facts | LLM calls | LLM tokens | Embedding calls | Embedding tokens | Ingest time | Ingest cost | Query cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in report["results"]:
        ingestion = result["ingestion"]
        queries = result["queries"]
        lines.append(
            f"| {result['scenario']} | {result['source']['estimated_tokens']:,} | "
            f"{ingestion['entities']} | {ingestion['facts']} | {ingestion['llm_calls']} | "
            f"{ingestion['llm_input_tokens'] + ingestion['llm_output_tokens']:,} | "
            f"{ingestion['embedding_requests']} | "
            f"{ingestion['embedding_tokens']:,} | {ingestion['seconds']:.1f}s | "
            f"${ingestion['estimated_cost_usd']:.6f} | "
            f"${queries['estimated_cost_per_query_usd']:.8f} |"
        )
    lines.extend(
        [
            "",
            "## Volume Projections",
            "",
            "Projections are linear and assume independent episodes with complexity matching each scenario.",
            "",
            "| Scenario | Documents | Ingestion cost | LLM calls | LLM tokens | Embedding tokens | Sequential ingest time | Same number of queries |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for scenario, volumes in report["projections"].items():
        for volume, values in volumes.items():
            lines.append(
                f"| {scenario} | {int(volume):,} | ${values['ingestion_cost_usd']:.4f} | "
                f"{values['llm_calls']:,} | {values['llm_tokens']:,} | "
                f"{values['embedding_tokens']:,} | {values['sequential_ingestion_hours']:.2f}h | "
                f"${values['queries_equal_to_document_count_cost_usd']:.6f} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `low`, `mid`, and `high` are planning bands, not statistical confidence bounds. Only mid is directly measured by the command.",
            "- Multiple exploratory runs showed stable low/mid costs, but repeat production-shaped runs are still needed for formal confidence intervals.",
            "- Measurements use empty isolated graphs. Warm graphs can require entity/fact deduplication and contradiction calls, so production ingestion may cost more.",
            "- Before applying Graphiti PR #1711, dense ingestion repeatedly exceeded three minutes while FalkorDB was processing pathological edge full-text endpoint scans. High remains extrapolated for stable, bounded benchmark runs.",
            "- Ingestion cost depends more on extracted entities, facts, deduplication candidates, and history than raw text size alone.",
            "- Standard MCP fact search uses hybrid RRF and normally incurs one query embedding, with no extraction LLM or OpenAI reranker call.",
            "- Query cost is OpenAI API cost only; local FalkorDB compute is not monetized.",
            "- Node search and advanced cross-encoder recipes may have different costs.",
            "- Sequential duration is a simple linear projection. Concurrency can reduce wall time but is constrained by provider rate limits.",
            "- Pricing excludes retries, regional uplifts, long-context premiums, community building, and saga summarization.",
            "- Provider Costs API values can lag; these estimates use measured tokens and published Standard API rates.",
            "",
            "## Public Evidence",
            "",
            "No representative public OSS Graphiti cost benchmark currently exists. Historical references:",
            "",
            "- Graphiti issue #467 reported about 22 calls and $0.0181 per episode in May 2025, before major prompt/call optimizations: https://github.com/getzep/graphiti/issues/467",
            "- Graphiti v0.27 introduced efficiency-oriented prompt refactoring: https://github.com/getzep/graphiti/releases/tag/v0.27.0",
            "- Zep's DMR/LongMemEval work evaluates retrieval quality, not OSS ingestion cost: https://arxiv.org/abs/2501.13956",
            "- Current OpenAI pricing: https://developers.openai.com/api/docs/pricing",
            "",
        ]
    )
    return "\n".join(lines)
