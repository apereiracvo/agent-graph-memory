from __future__ import annotations

import math

import pytest

from agent_graph_memory.falkordb_hotpath_benchmark import (
    GRAPH_PREFIX,
    PROTOTYPE_COUNT,
    RELATIONSHIP_FULLTEXT_QUERY,
    VECTOR_DIMENSIONS,
    _assert_safe_graph_name,
    _percentiles,
    _seed_range,
    _validate_arguments,
    edge_row,
    entity_count_to_edge_count,
    episode_projection,
    node_row,
    prototype_vector,
)


def test_vectors_and_dataset_counts_are_deterministic() -> None:
    first = prototype_vector(3)

    assert first == prototype_vector(3 + PROTOTYPE_COUNT)
    assert first != prototype_vector(4)
    assert len(first) == VECTOR_DIMENSIONS
    assert math.isclose(sum(value * value for value in first), 1.0)
    assert entity_count_to_edge_count(100) == 150
    assert entity_count_to_edge_count(501) == 751
    assert node_row(7) == node_row(7)
    assert edge_row(11, 100) == edge_row(11, 100)
    assert edge_row(11, 100) == edge_row(11, 1_000)


def test_seed_range_bounds_batches_and_covers_each_index_once() -> None:
    class Graph:
        def __init__(self) -> None:
            self.batches: list[list[int]] = []

        def query(self, query: str, *, params: dict[str, object], timeout: int) -> None:
            self.batches.append([row["index"] for row in params["rows"]])

    graph = Graph()
    _seed_range(
        graph,
        "seed",
        5,
        38,
        lambda index: {"index": index},
        "graph",
        "now",
        3,
        100,
    )

    assert sorted(index for batch in graph.batches for index in batch) == list(range(5, 38))
    assert max(map(len, graph.batches)) == 3


def test_graph_prefix_guard_requires_full_generated_shape() -> None:
    safe = f"{GRAPH_PREFIX}20260826T120000Z_0123abcd"
    _assert_safe_graph_name(safe)

    for unsafe in (
        "agent_graph_memory",
        GRAPH_PREFIX,
        f"{GRAPH_PREFIX}../other",
        f"x{safe}",
        f"{safe}_extra",
    ):
        with pytest.raises(ValueError, match="unsafe benchmark graph"):
            _assert_safe_graph_name(unsafe)


def test_relationship_fulltext_uses_direct_endpoints_and_parameters() -> None:
    assert "queryRelationships('RELATES_TO', $query)" in RELATIONSHIP_FULLTEXT_QUERY
    assert "startNode(rel) AS n" in RELATIONSHIP_FULLTEXT_QUERY
    assert "endNode(rel) AS m" in RELATIONSHIP_FULLTEXT_QUERY
    assert "WHERE n:Entity AND m:Entity" in RELATIONSHIP_FULLTEXT_QUERY
    assert "MATCH (n:Entity)-[e:RELATES_TO" not in RELATIONSHIP_FULLTEXT_QUERY
    assert "$group_ids" in RELATIONSHIP_FULLTEXT_QUERY
    assert "$limit" in RELATIONSHIP_FULLTEXT_QUERY


def test_statistics_retain_errors_and_compute_p50_and_max() -> None:
    summary = _percentiles(
        [
            {"wall_ms": 1, "client_ms": 2, "server_ms": 0.5, "result_count": 3, "error": None},
            {"wall_ms": 9, "client_ms": 10, "server_ms": 7, "result_count": 5, "error": None},
            {"wall_ms": 20, "client_ms": 20, "server_ms": 0, "result_count": 0, "error": "timeout"},
        ]
    )

    assert summary["successes"] == 2
    assert summary["errors"] == ["timeout"]
    assert summary["wall_ms"] == {"p50": 5.0, "max": 9.0}
    assert summary["result_count"] == {"p50": 4.0, "max": 5}


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (((1,), 0, 1, 1, 1, 1), "plateaus"),
        (((10, 10), 0, 1, 1, 1, 1), "strictly increasing"),
        (((10,), -1, 1, 1, 1, 1), "warmups"),
        (((10,), 0, 0, 1, 1, 1), "samples"),
        (((10,), 0, 1, 0, 1, 1), "timeout"),
        (((10,), 0, 1, 1, 0, 1), "batch"),
        (((10,), 0, 1, 1, 1, 0), "limit"),
    ],
)
def test_argument_validation(values: tuple[object, ...], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _validate_arguments(*values)


def test_episode_projection_formula() -> None:
    phases = {
        "node_cosine": {"summary": {"wall_ms": {"p50": 4.0}}},
        "edge_hybrid_db": {"summary": {"wall_ms": {"p50": 6.0}}},
    }

    projection = episode_projection(phases, 3, 2, 5)

    assert projection["entity_resolution_ms"] == 12.0
    assert projection["fact_resolution_ms"] == 24.0
    assert projection["retrieval_ms"] == 30.0
    assert projection["projected_db_overhead_ms"] == 66.0
