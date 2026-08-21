from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver


def group_id() -> str:
    return os.getenv("GRAPHITI_GROUP_ID", "agent_graph_memory")


@asynccontextmanager
async def graphiti_client() -> AsyncIterator[Graphiti]:
    group = group_id()
    driver = FalkorDriver(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        password=os.getenv("FALKORDB_PASSWORD") or None,
        database=group,
    )
    client = Graphiti(graph_driver=driver)
    try:
        await client.build_indices_and_constraints()
        yield client
    finally:
        await client.close()
