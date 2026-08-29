from __future__ import annotations

import inspect
import json
import math
import os
import platform
import re
import statistics
import time
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import uuid4

GRAPH_PREFIX = "graphiti_hotpath_bench_"
DEFAULT_PLATEAUS = (100, 500, 1_000, 2_500, 5_000, 10_000)
VECTOR_DIMENSIONS = 1_536
PROTOTYPE_COUNT = 8
EDGE_RATIO = 1.5
DEFAULT_BATCH_SIZE = 100
DEFAULT_WARMUPS = 2
DEFAULT_SAMPLES = 5
DEFAULT_QUERY_TIMEOUT_MS = 30_000
DEFAULT_LIMIT = 20

_GRAPH_NAME = re.compile(r"^graphiti_hotpath_bench_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")
_STOPWORDS = [
    "a",
    "is",
    "the",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "if",
    "in",
    "into",
    "it",
    "no",
    "not",
    "of",
    "on",
    "or",
    "such",
    "that",
    "their",
    "then",
    "there",
    "these",
    "they",
    "this",
    "to",
    "was",
    "will",
    "with",
]

INDEX_QUERIES = (
    "CREATE INDEX FOR (n:Entity) ON (n.uuid, n.group_id, n.name, n.created_at)",
    (
        "CREATE INDEX FOR ()-[e:RELATES_TO]-() ON "
        "(e.uuid, e.group_id, e.name, e.created_at, e.expired_at, e.valid_at, e.invalid_at)"
    ),
    (
        f"CALL db.idx.fulltext.createNodeIndex({{label: 'Entity', stopwords: {_STOPWORDS!r}}}, "
        "'name', 'summary', 'group_id')"
    ),
    "CREATE FULLTEXT INDEX FOR ()-[e:RELATES_TO]-() ON (e.name, e.fact, e.group_id)",
)

SEED_NODES_QUERY = """
UNWIND $rows AS row
CREATE (n:Entity)
SET n.uuid = row.uuid,
    n.group_id = $group_id,
    n.name = row.name,
    n.summary = row.summary,
    n.created_at = $created_at,
    n.name_embedding = vecf32($vector)
"""

SEED_EDGES_QUERY = """
UNWIND $rows AS row
MATCH (source:Entity {uuid: row.source_uuid})
MATCH (target:Entity {uuid: row.target_uuid})
CREATE (source)-[e:RELATES_TO]->(target)
SET e.uuid = row.uuid,
    e.group_id = $group_id,
    e.name = row.name,
    e.fact = row.fact,
    e.episodes = [],
    e.created_at = $created_at,
    e.expired_at = null,
    e.valid_at = $created_at,
    e.invalid_at = null,
    e.fact_embedding = vecf32($vector)
"""

NODE_COSINE_QUERY = """
MATCH (n:Entity)
WHERE n.group_id IN $group_ids
WITH n, (2 - vec.cosineDistance(n.name_embedding, vecf32($search_vector))) / 2 AS score
WHERE score > $min_score
RETURN n.uuid AS uuid, score
ORDER BY score DESC
LIMIT $limit
"""

EDGE_COSINE_QUERY = """
MATCH (n:Entity)-[e:RELATES_TO]->(m:Entity)
WHERE e.group_id IN $group_ids
WITH DISTINCT e, n, m,
    (2 - vec.cosineDistance(e.fact_embedding, vecf32($search_vector))) / 2 AS score
WHERE score > $min_score
RETURN e.uuid AS uuid, score
ORDER BY score DESC
LIMIT $limit
"""

NODE_FULLTEXT_QUERY = """
CALL db.idx.fulltext.queryNodes('Entity', $query)
YIELD node AS n, score
WHERE n.group_id IN $group_ids
RETURN n.uuid AS uuid, score
ORDER BY score DESC
LIMIT $limit
"""

# Graphiti 0.29.3's relationship fulltext query with the local PR #1711 endpoint patch.
RELATIONSHIP_FULLTEXT_QUERY = """
CALL db.idx.fulltext.queryRelationships('RELATES_TO', $query)
YIELD relationship AS rel, score
WITH rel AS e, score, startNode(rel) AS n, endNode(rel) AS m
WHERE n:Entity AND m:Entity
WITH e, score, n, m
WHERE e.group_id IN $group_ids
RETURN e.uuid AS uuid, n.uuid AS source_node_uuid, m.uuid AS target_node_uuid, score
ORDER BY score DESC
LIMIT $limit
"""

RELATIONSHIP_FULLTEXT_COUNT_QUERY = """
CALL db.idx.fulltext.queryRelationships('RELATES_TO', $query)
YIELD relationship AS rel
WITH rel AS e, startNode(rel) AS n, endNode(rel) AS m
WHERE n:Entity AND m:Entity AND e.group_id IN $group_ids
RETURN count(e) AS fulltext_hit_count
"""


def entity_count_to_edge_count(entity_count: int) -> int:
    return entity_count * 3 // 2


def prototype_vector(index: int) -> tuple[float, ...]:
    """Return one of a small deterministic set of normalized vectors."""
    prototype = index % PROTOTYPE_COUNT
    magnitude = 1.0 / math.sqrt(VECTOR_DIMENSIONS)
    return tuple(
        magnitude if ((dimension * 17 + prototype * 31) % 19) < 10 else -magnitude
        for dimension in range(VECTOR_DIMENSIONS)
    )


def node_row(index: int) -> dict[str, str]:
    topic = index % 20
    return {
        "uuid": f"entity-{index:08d}",
        "name": f"Benchmark Entity {index:08d} benchmarktopic{topic:02d}",
        "summary": f"benchmarkcommon deterministic synthetic entity topic {topic:02d}",
    }


def edge_row(index: int, entity_count: int) -> dict[str, str]:
    source = index * 2 // 3
    if source >= entity_count:
        raise ValueError("edge index is outside the entity plateau")
    target = source - 1 if source else 1
    topic = index % 20
    return {
        "uuid": f"edge-{index:08d}",
        "source_uuid": f"entity-{source:08d}",
        "target_uuid": f"entity-{target:08d}",
        "name": f"benchmarkrelation benchmarktopic{topic:02d}",
        "fact": f"benchmarkcommon synthetic relationship fact benchmarktopic{topic:02d}",
    }


def _assert_safe_graph_name(graph_name: str) -> None:
    if not graph_name.startswith(GRAPH_PREFIX) or not _GRAPH_NAME.fullmatch(graph_name):
        raise ValueError(f"Refusing unsafe benchmark graph name: {graph_name!r}")


def _validate_arguments(
    plateaus: tuple[int, ...],
    warmups: int,
    samples: int,
    query_timeout_ms: int,
    batch_size: int,
    limit: int,
) -> None:
    if not plateaus or any(value < 2 for value in plateaus):
        raise ValueError("plateaus must contain entity counts of at least 2")
    if tuple(sorted(set(plateaus))) != plateaus:
        raise ValueError("plateaus must be strictly increasing and unique")
    if warmups < 0:
        raise ValueError("warmups must be non-negative")
    if samples < 1:
        raise ValueError("samples must be positive")
    if query_timeout_ms < 1:
        raise ValueError("query timeout must be positive")
    if batch_size < 1:
        raise ValueError("batch size must be positive")
    if limit < 1:
        raise ValueError("result limit must be positive")


def _fulltext_query(graph_name: str, term: str) -> str:
    escaped_group = re.sub(r"([^a-zA-Z0-9])", r"\\\1", graph_name)
    return f'(@group_id:"{escaped_group}") ({term})'


def _percentiles(samples: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [sample for sample in samples if sample.get("error") is None]
    errors = [sample["error"] for sample in samples if sample.get("error") is not None]

    def metric(name: str) -> dict[str, float | None]:
        values = [float(sample[name]) for sample in successful]
        return {
            "p50": round(statistics.median(values), 3) if values else None,
            "max": round(max(values), 3) if values else None,
        }

    result_counts = [int(sample["result_count"]) for sample in successful]
    return {
        "attempts": len(samples),
        "successes": len(successful),
        "errors": errors,
        "wall_ms": metric("wall_ms"),
        "client_ms": metric("client_ms"),
        "server_ms": metric("server_ms"),
        "result_count": {
            "p50": statistics.median(result_counts) if result_counts else None,
            "max": max(result_counts) if result_counts else None,
        },
    }


def episode_projection(
    phases: dict[str, dict[str, Any]],
    entities_per_episode: float,
    facts_per_episode: float,
    searches_per_query: float,
) -> dict[str, float]:
    if min(entities_per_episode, facts_per_episode, searches_per_query) < 0:
        raise ValueError("episode projection inputs must be non-negative")

    def p50(phase: str) -> float:
        value = phases[phase]["summary"]["wall_ms"]["p50"]
        if value is None:
            raise ValueError(f"phase {phase!r} has no successful samples")
        return float(value)

    entity_ms = entities_per_episode * p50("node_cosine")
    # Graphiti performs endpoint duplicate and graph-wide invalidation searches per fact.
    fact_ms = facts_per_episode * 2 * p50("edge_hybrid_db")
    retrieval_ms = searches_per_query * p50("edge_hybrid_db")
    return {
        "entities_per_episode": entities_per_episode,
        "facts_per_episode": facts_per_episode,
        "searches_per_query": searches_per_query,
        "entity_resolution_ms": round(entity_ms, 3),
        "fact_resolution_ms": round(fact_ms, 3),
        "retrieval_ms": round(retrieval_ms, 3),
        "projected_db_overhead_ms": round(entity_ms + fact_ms + retrieval_ms, 3),
    }


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _pairs(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple)) and len(value) % 2 == 0:
        return {str(value[index]): _pairs(value[index + 1]) for index in range(0, len(value), 2)}
    return value


def _query(graph: Any, cypher: str, params: dict[str, Any], timeout_ms: int) -> Any:
    kwargs: dict[str, Any] = {"params": params}
    try:
        if "timeout" in inspect.signature(graph.query).parameters:
            kwargs["timeout"] = timeout_ms
    except (TypeError, ValueError):
        pass
    return graph.query(cypher, **kwargs)


def _single_query_sample(
    graph: Any, cypher: str, params: dict[str, Any], timeout_ms: int
) -> dict[str, Any]:
    wall_started = time.perf_counter()
    client_started = time.perf_counter()
    try:
        result = _query(graph, cypher, params, timeout_ms)
        client_ms = (time.perf_counter() - client_started) * 1_000
        return {
            "wall_ms": round((time.perf_counter() - wall_started) * 1_000, 3),
            "client_ms": round(client_ms, 3),
            "server_ms": round(float(result.run_time_ms), 3),
            "result_count": len(result.result_set),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - driver errors are benchmark results.
        elapsed = (time.perf_counter() - wall_started) * 1_000
        return {
            "wall_ms": round(elapsed, 3),
            "client_ms": round(elapsed, 3),
            "server_ms": 0.0,
            "result_count": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _compound_sample(
    graph: Any, queries: tuple[tuple[str, dict[str, Any]], ...], timeout_ms: int
) -> dict[str, Any]:
    started = time.perf_counter()
    components = [
        _single_query_sample(graph, cypher, params, timeout_ms) for cypher, params in queries
    ]
    errors = [component["error"] for component in components if component["error"]]
    return {
        "wall_ms": round((time.perf_counter() - started) * 1_000, 3),
        "client_ms": round(sum(component["client_ms"] for component in components), 3),
        "server_ms": round(sum(component["server_ms"] for component in components), 3),
        "result_count": sum(component["result_count"] for component in components),
        "error": "; ".join(errors) if errors else None,
        "components": components,
    }


def _measure_phase(
    graph: Any,
    queries: tuple[tuple[str, dict[str, Any]], ...],
    warmups: int,
    samples: int,
    timeout_ms: int,
) -> dict[str, Any]:
    run = _single_query_sample if len(queries) == 1 else _compound_sample
    for _ in range(warmups):
        if len(queries) == 1:
            run(graph, queries[0][0], queries[0][1], timeout_ms)
        else:
            run(graph, queries, timeout_ms)
    raw = []
    for _ in range(samples):
        if len(queries) == 1:
            raw.append(run(graph, queries[0][0], queries[0][1], timeout_ms))
        else:
            raw.append(run(graph, queries, timeout_ms))
    return {"raw_samples": raw, "summary": _percentiles(raw)}


def _seed_range(
    graph: Any,
    query: str,
    start: int,
    stop: int,
    row_factory: Callable[[int], dict[str, str]],
    graph_name: str,
    created_at: str,
    batch_size: int,
    timeout_ms: int,
) -> None:
    for prototype in range(PROTOTYPE_COUNT):
        vector = prototype_vector(prototype)
        rows: list[dict[str, str]] = []
        first = start + (prototype - start) % PROTOTYPE_COUNT
        for index in range(first, stop, PROTOTYPE_COUNT):
            rows.append(row_factory(index))
            if len(rows) < batch_size:
                continue
            _query(
                graph,
                query,
                {
                    "rows": rows,
                    "group_id": graph_name,
                    "created_at": created_at,
                    "vector": vector,
                },
                timeout_ms,
            )
            rows = []
        if rows:
            _query(
                graph,
                query,
                {
                    "rows": rows,
                    "group_id": graph_name,
                    "created_at": created_at,
                    "vector": vector,
                },
                timeout_ms,
            )


def _seed_plateau(
    graph: Any,
    graph_name: str,
    previous_entities: int,
    entity_count: int,
    batch_size: int,
    timeout_ms: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    created_at = "2026-01-01T00:00:00+00:00"
    _seed_range(
        graph,
        SEED_NODES_QUERY,
        previous_entities,
        entity_count,
        node_row,
        graph_name,
        created_at,
        batch_size,
        timeout_ms,
    )

    previous_edges = entity_count_to_edge_count(previous_entities)
    edge_count = entity_count_to_edge_count(entity_count)
    _seed_range(
        graph,
        SEED_EDGES_QUERY,
        previous_edges,
        edge_count,
        lambda index: edge_row(index, entity_count),
        graph_name,
        created_at,
        batch_size,
        timeout_ms,
    )
    return {
        "entities_added": entity_count - previous_entities,
        "facts_added": edge_count - previous_edges,
        "wall_ms": round((time.perf_counter() - started) * 1_000, 3),
    }


def _memory(client: Any, graph_name: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        info = client.execute_command("INFO", "MEMORY")
        if isinstance(info, dict):
            result["redis"] = {
                key: info.get(key)
                for key in ("used_memory", "used_memory_rss", "used_memory_peak", "maxmemory")
            }
        else:
            values = {}
            for line in str(info).splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    if key in {"used_memory", "used_memory_rss", "used_memory_peak", "maxmemory"}:
                        values[key] = int(value)
            result["redis"] = values
    except Exception as exc:  # noqa: BLE001 - optional server metric.
        result["redis_error"] = f"{type(exc).__name__}: {exc}"
    try:
        result["graph_mb"] = _pairs(
            client.execute_command("GRAPH.MEMORY", "USAGE", graph_name, "SAMPLES", 100)
        )
    except Exception as exc:  # noqa: BLE001 - command availability is version-dependent.
        result["graph_memory_error"] = f"{type(exc).__name__}: {exc}"
    return result


def _configuration(client: Any) -> dict[str, Any]:
    try:
        return {"graph_config": _pairs(client.execute_command("GRAPH.CONFIG", "GET", "*"))}
    except Exception as exc:  # noqa: BLE001 - command availability/ACL is server-dependent.
        return {"graph_config_error": f"{type(exc).__name__}: {exc}"}


def _phase_queries(
    graph_name: str, limit: int
) -> dict[str, tuple[tuple[str, dict[str, Any]], ...]]:
    vector_params = {
        "group_ids": [graph_name],
        "search_vector": prototype_vector(3),
        "min_score": -1.0,
        "limit": limit,
    }
    typical = {
        "query": _fulltext_query(graph_name, "benchmarktopic07"),
        "group_ids": [graph_name],
        "limit": limit,
    }
    broad = {
        "query": _fulltext_query(graph_name, "benchmarkcommon"),
        "group_ids": [graph_name],
        "limit": limit,
    }
    node_text = {
        "query": _fulltext_query(graph_name, "benchmarktopic07"),
        "group_ids": [graph_name],
        "limit": limit,
    }
    return {
        "node_cosine": ((NODE_COSINE_QUERY, vector_params),),
        "edge_cosine": ((EDGE_COSINE_QUERY, vector_params),),
        "relationship_fulltext_typical": ((RELATIONSHIP_FULLTEXT_QUERY, typical),),
        "relationship_fulltext_broad": ((RELATIONSHIP_FULLTEXT_QUERY, broad),),
        "node_hybrid_db": (
            (NODE_FULLTEXT_QUERY, node_text),
            (NODE_COSINE_QUERY, vector_params),
        ),
        "edge_hybrid_db": (
            (RELATIONSHIP_FULLTEXT_QUERY, typical),
            (EDGE_COSINE_QUERY, vector_params),
        ),
    }


def _fulltext_hits(graph: Any, graph_name: str, timeout_ms: int) -> dict[str, Any]:
    hits: dict[str, Any] = {}
    for name, term in (("typical", "benchmarktopic07"), ("broad", "benchmarkcommon")):
        try:
            result = _query(
                graph,
                RELATIONSHIP_FULLTEXT_COUNT_QUERY,
                {"query": _fulltext_query(graph_name, term), "group_ids": [graph_name]},
                timeout_ms,
            )
            hits[name] = {
                "count": int(result.result_set[0][0]) if result.result_set else 0,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 - a timed-out count belongs in the report.
            hits[name] = {"count": None, "error": f"{type(exc).__name__}: {exc}"}
    return hits


def _metadata(client: Any, graph_name: str, timeout_supported: bool) -> dict[str, Any]:
    metadata = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {
            "agent-graph-memory": _package_version("agent-graph-memory"),
            "graphiti-core": _package_version("graphiti-core"),
            "falkordb": _package_version("falkordb"),
            "redis": _package_version("redis"),
        },
        "graph": graph_name,
        "query_timeout_supported": timeout_supported,
        "openai_calls": 0,
    }
    try:
        info = client.execute_command("INFO", "SERVER")
        metadata["redis_server"] = info if isinstance(info, dict) else str(info)
    except Exception as exc:  # noqa: BLE001 - optional server metadata.
        metadata["redis_server_error"] = f"{type(exc).__name__}: {exc}"
    return metadata


def _markdown(report: dict[str, Any]) -> str:
    config = report["configuration"]
    lines = [
        "# FalkorDB Graphiti Hot-Path Growth Benchmark",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        (
            "This benchmark performs no OpenAI calls. Times are milliseconds; graph memory is "
            "reported by FalkorDB in MB where supported."
        ),
        "",
        "## Configuration",
        "",
        f"- FalkorDB: `{config['host']}:{config['port']}`",
        f"- Plateaus: `{', '.join(str(value) for value in config['plateaus'])}` entities",
        f"- Warmups/samples: `{config['warmups']}/{config['samples']}`",
        f"- Query timeout: `{config['query_timeout_ms']} ms`",
        f"- Vector dimensions/prototypes: `{VECTOR_DIMENSIONS}/{PROTOTYPE_COUNT}`",
        "",
        "## Growth Curves",
        "",
        "| N entities | F facts | Redis used | Graph MB | Node cosine p50/max | Edge cosine p50/max | Edge FT typical hits/p50 | Edge FT broad hits/p50 | Edge hybrid p50 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for point in report["curves"]:
        phases = point["phases"]
        memory = point["memory"]
        redis_used = memory.get("redis", {}).get("used_memory")
        graph_mb = memory.get("graph_mb", {}).get("total_graph_sz_mb")

        def timing(
            name: str, include_max: bool = False, phase_results: dict[str, Any] = phases
        ) -> str:
            values = phase_results[name]["summary"]["wall_ms"]
            if values["p50"] is None:
                return "error"
            return (
                f"{values['p50']:.3f}/{values['max']:.3f}"
                if include_max
                else f"{values['p50']:.3f}"
            )

        lines.append(
            f"| {point['N_entities']:,} | {point['F_facts']:,} | "
            f"{redis_used if redis_used is not None else 'n/a'} | "
            f"{graph_mb if graph_mb is not None else 'n/a'} | "
            f"{timing('node_cosine', True)} | {timing('edge_cosine', True)} | "
            f"{point['fulltext_hits']['typical']['count']}/{timing('relationship_fulltext_typical')} | "
            f"{point['fulltext_hits']['broad']['count']}/{timing('relationship_fulltext_broad')} | "
            f"{timing('edge_hybrid_db')} |"
        )
    lines.extend(
        [
            "",
            "## Forecasting",
            "",
            (
                "Each JSON curve point contains raw samples for N (entities) and F (facts). The "
                "`episode_projection` object applies measured hybrid DB p50 values to E extracted "
                "entities, episode facts, and Q searches; it excludes model and application time."
            ),
            "",
            "## Cleanup",
            "",
            f"- Exact benchmark graph deleted: `{report['cleanup']['deleted']}`",
            f"- Absence verified with GRAPH.LIST: `{report['cleanup']['verified_absent']}`",
            "",
        ]
    )
    return "\n".join(lines)


def run_benchmark(
    output_dir: Path,
    *,
    plateaus: tuple[int, ...] = DEFAULT_PLATEAUS,
    warmups: int = DEFAULT_WARMUPS,
    samples: int = DEFAULT_SAMPLES,
    query_timeout_ms: int = DEFAULT_QUERY_TIMEOUT_MS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int = DEFAULT_LIMIT,
) -> tuple[Path, Path]:
    """Run the local FalkorDB-only growth benchmark and write JSON/Markdown reports."""
    _validate_arguments(plateaus, warmups, samples, query_timeout_ms, batch_size, limit)
    from falkordb import FalkorDB

    generated = datetime.now(UTC)
    run_id = generated.strftime("%Y%m%dT%H%M%SZ")
    run_suffix = uuid4().hex[:8]
    graph_name = f"{GRAPH_PREFIX}{run_id}_{run_suffix}"
    _assert_safe_graph_name(graph_name)
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    password = os.getenv("FALKORDB_PASSWORD") or None
    client = FalkorDB(host=host, port=port, password=password)
    graph = client.select_graph(graph_name)
    owns_graph = False
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": generated.isoformat(),
        "benchmark": "graphiti_falkordb_hotpath_growth",
        "zero_openai_cost": True,
        "configuration": {
            "host": host,
            "port": port,
            "password_configured": password is not None,
            "plateaus": list(plateaus),
            "warmups": warmups,
            "samples": samples,
            "query_timeout_ms": query_timeout_ms,
            "batch_size": batch_size,
            "result_limit": limit,
            "vector_dimensions": VECTOR_DIMENSIONS,
            "prototype_count": PROTOTYPE_COUNT,
            "edge_ratio": EDGE_RATIO,
        },
        "curves": [],
        "cleanup": {"graph": graph_name, "deleted": False, "verified_absent": False},
    }
    failure: BaseException | None = None
    try:
        existing_graphs = set(client.list_graphs())
        if graph_name in existing_graphs:
            raise RuntimeError(f"Benchmark graph collision: {graph_name}")
        owns_graph = True
        timeout_supported = "timeout" in inspect.signature(graph.query).parameters
        report["metadata"] = _metadata(client, graph_name, timeout_supported)
        report["server_configuration"] = _configuration(client)
        report["baseline_memory"] = _memory(client, graph_name)
        for query in INDEX_QUERIES:
            _query(graph, query, {}, query_timeout_ms)

        previous_entities = 0
        for entity_count in plateaus:
            print(f"[{entity_count:,} entities] seeding and probing", flush=True)
            seed = _seed_plateau(
                graph,
                graph_name,
                previous_entities,
                entity_count,
                batch_size,
                query_timeout_ms,
            )
            phase_results = {
                name: _measure_phase(graph, queries, warmups, samples, query_timeout_ms)
                for name, queries in _phase_queries(graph_name, limit).items()
            }
            try:
                projection = episode_projection(phase_results, 1.0, 1.0, 1.0)
            except ValueError as exc:
                projection = {"error": str(exc)}
            point = {
                "N_entities": entity_count,
                "F_facts": entity_count_to_edge_count(entity_count),
                "edge_ratio": EDGE_RATIO,
                "seed": seed,
                "fulltext_hits": _fulltext_hits(graph, graph_name, query_timeout_ms),
                "memory": _memory(client, graph_name),
                "phases": phase_results,
                "episode_projection": projection,
            }
            report["curves"].append(point)
            previous_entities = entity_count
        report["forecasting"] = {
            "symbols": {
                "E": "entities extracted per episode",
                "N": "stored Entity nodes at the plateau",
                "F": "facts extracted per episode; F_facts is stored RELATES_TO cardinality",
                "Q": "hybrid searches per user query",
            },
            "formula": "E*node_cosine_p50 + 2*F*edge_hybrid_db_p50 + Q*edge_hybrid_db_p50",
            "units": "milliseconds of serial database wall time",
            "caveat": "A DB-only linear projection; model calls, concurrency, and cache interactions are excluded.",
        }
    except Exception as exc:  # noqa: BLE001 - preserve a partial report for any run failure.
        failure = exc
        report["run_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            if owns_graph and graph_name in set(client.list_graphs()):
                _assert_safe_graph_name(graph_name)
                graph.delete()  # Issues GRAPH.DELETE for this exact graph only.
                report["cleanup"]["deleted"] = True
            report["cleanup"]["verified_absent"] = graph_name not in set(client.list_graphs())
            if owns_graph and not report["cleanup"]["verified_absent"]:
                raise RuntimeError(f"Cleanup verification failed for {graph_name}")
        except Exception as cleanup_exc:  # noqa: BLE001 - never hide cleanup failure details.
            report["cleanup"]["error"] = f"{type(cleanup_exc).__name__}: {cleanup_exc}"
            if failure is None:
                failure = cleanup_exc
        finally:
            client.close()

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"falkordb-hotpath-{run_id}-{run_suffix}.json"
    markdown_path = output_dir / f"falkordb-hotpath-{run_id}-{run_suffix}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    if failure is not None:
        raise RuntimeError(
            f"Benchmark failed; partial report written to {json_path}: {failure}"
        ) from failure
    return json_path, markdown_path
