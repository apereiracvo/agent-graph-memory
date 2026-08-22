from pathlib import Path

import pytest

from agent_graph_memory.compat import (
    FALKORDB_FIXED_QUERY,
    FALKORDB_OLD_QUERY,
    GPT56_FIXED,
    GPT56_OLD,
    patch_graphiti_core,
    patch_mcp_server,
)


def test_patches_are_idempotent(tmp_path: Path) -> None:
    graphiti = tmp_path / "graphiti"
    search = graphiti / "search"
    search.mkdir(parents=True)
    (search / "search_utils.py").write_text(FALKORDB_OLD_QUERY)
    mcp = tmp_path / "mcp"
    factories = mcp / "src" / "services"
    factories.mkdir(parents=True)
    (factories / "factories.py").write_text(GPT56_OLD)

    assert patch_graphiti_core(graphiti)
    assert patch_mcp_server(mcp)
    assert not patch_graphiti_core(graphiti)
    assert not patch_mcp_server(mcp)
    assert FALKORDB_FIXED_QUERY in (search / "search_utils.py").read_text()
    assert GPT56_FIXED in (factories / "factories.py").read_text()


def test_refuses_unknown_upstream_source(tmp_path: Path) -> None:
    search = tmp_path / "search"
    search.mkdir()
    (search / "search_utils.py").write_text("unexpected")

    with pytest.raises(RuntimeError, match="Refusing to patch"):
        patch_graphiti_core(tmp_path)
