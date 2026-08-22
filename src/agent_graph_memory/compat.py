from __future__ import annotations

import importlib.util
from pathlib import Path

FALKORDB_OLD_QUERY = '''    match_query = """
    YIELD relationship AS rel, score
    MATCH (n:Entity)-[e:RELATES_TO {uuid: rel.uuid}]->(m:Entity)
    """
    if driver.provider == GraphProvider.KUZU:
'''

FALKORDB_FIXED_QUERY = '''    match_query = """
    YIELD relationship AS rel, score
    MATCH (n:Entity)-[e:RELATES_TO {uuid: rel.uuid}]->(m:Entity)
    """
    if driver.provider == GraphProvider.FALKORDB:
        # PR #1711: avoid an Entity label scan for every full-text relationship hit.
        match_query = """
        YIELD relationship AS rel, score
        WITH rel AS e, score, startNode(rel) AS n, endNode(rel) AS m
        WHERE n:Entity AND m:Entity
        WITH e, score, n, m
        """
    if driver.provider == GraphProvider.KUZU:
'''

GPT56_OLD = "model.startswith('gpt-5.5')"
GPT56_FIXED = "model.startswith(('gpt-5.5', 'gpt-5.6'))"


def _replace_once(path: Path, old: str, new: str) -> bool:
    source = path.read_text(encoding="utf-8")
    if new in source:
        return False
    if source.count(old) != 1:
        raise RuntimeError(f"Refusing to patch unexpected upstream source: {path}")
    path.write_text(source.replace(old, new), encoding="utf-8")
    return True


def patch_graphiti_core(root: Path | None = None) -> bool:
    if root is None:
        spec = importlib.util.find_spec("graphiti_core")
        if spec is None or spec.submodule_search_locations is None:
            raise RuntimeError("graphiti_core is not installed")
        root = Path(next(iter(spec.submodule_search_locations)))
    return _replace_once(root / "search" / "search_utils.py", FALKORDB_OLD_QUERY, FALKORDB_FIXED_QUERY)


def patch_mcp_server(root: Path) -> bool:
    return _replace_once(root / "src" / "services" / "factories.py", GPT56_OLD, GPT56_FIXED)
