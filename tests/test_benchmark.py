from agent_graph_memory.benchmark import _cost, _markdown, scenarios


def test_scenarios_define_planning_bands() -> None:
    corpus = scenarios("gpt-5.6-luna")

    assert [scenario.name for scenario in corpus] == ["low", "mid", "high"]
    assert len(corpus[0].body) < len(corpus[1].body) < len(corpus[2].body)
    assert len(corpus[0].queries) < len(corpus[1].queries) < len(corpus[2].queries)


def test_cost_uses_published_token_rates() -> None:
    assert _cost(1_000_000, 1_000_000, 1_000_000) == 1.42


def test_markdown_renders_results_and_projections() -> None:
    report = {
        "generated_at": "2026-08-21T00:00:00+00:00",
        "results": [
            {
                "scenario": "low",
                "source": {"estimated_tokens": 350},
                "ingestion": {
                    "entities": 3,
                    "facts": 2,
                    "llm_calls": 4,
                    "llm_input_tokens": 100,
                    "llm_output_tokens": 20,
                    "embedding_requests": 2,
                    "embedding_tokens": 50,
                    "seconds": 1.2,
                    "estimated_cost_usd": 0.001,
                },
                "queries": {"estimated_cost_per_query_usd": 0.000001},
            }
        ],
        "projections": {
            "low": {
                "100": {
                    "ingestion_cost_usd": 0.1,
                    "queries_equal_to_document_count_cost_usd": 0.0001,
                    "llm_calls": 400,
                    "llm_tokens": 12_000,
                    "embedding_tokens": 5_000,
                    "sequential_ingestion_hours": 0.03,
                }
            }
        },
    }

    markdown = _markdown(report)

    assert "| low | 350 |" in markdown
    assert "| low | 100 | $0.1000 |" in markdown
