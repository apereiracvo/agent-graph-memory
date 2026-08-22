# FalkorDB Performance Notes

## Confirmed Bottleneck

Graphiti `0.29.3` resolves endpoints after a FalkorDB relationship full-text search with:

```cypher
MATCH (n:Entity)-[e:RELATES_TO {uuid: rel.uuid}]->(m:Entity)
```

FalkorDB plans this as a full `:Entity` label scan for every relationship returned by the
full-text index. Complexity becomes `O(full-text hits x entities)`, even though the relationship
already knows both endpoints. During ingestion, Graphiti uses this search for fact deduplication
and contradiction detection, so the issue can make a queued episode appear to hang or be dropped.

The upstream fix in [Graphiti PR #1711](https://github.com/getzep/graphiti/pull/1711) reads the
relationship endpoints directly:

```cypher
WITH rel AS e, score, startNode(rel) AS n, endNode(rel) AS m
WHERE n:Entity AND m:Entity
```

The PR remains open and is not included in `graphiti-core==0.29.3` or Graphiti commit `993e081`.
This repository applies the exact provider-specific rewrite through
`scripts/patch_graphiti.py`. The patcher is idempotent and fails if upstream source no longer
matches, making an upgrade review explicit.

## Local Reproduction

Tested with the pinned FalkorDB image, 500 `Entity` nodes, 1,000 matching `RELATES_TO` edges, and a
50-result limit:

| Query | Result |
|---|---:|
| Graphiti 0.29.3 endpoint pattern | Timed out above the 1-second FalkorDB query limit |
| PR #1711 direct endpoints | 6.5 ms, 50 rows |

The original cost benchmark slowlog also showed dense full-text searches taking 10-14 seconds and
a nearly 1 MB dense edge-write payload taking about 10 seconds.

## Other Scaling Limits

- Node semantic deduplication runs one exhaustive vector scan per extracted entity. Graphiti does
  not create a FalkorDB vector index, so warm-graph work scales with extracted entities multiplied
  by existing entities.
- Graphiti's internal database gathers use the module-level `SEMAPHORE_LIMIT`, not
  `Graphiti(max_coroutines=...)` consistently. `.env.local` must therefore load before Graphiti is
  imported. The CLI now does this and uses `SEMAPHORE_LIMIT=5` by default.
- Canceling an asyncio task does not cancel work already queued inside FalkorDB. Repeated aborted
  runs can leave the query engine busy and make later fast queries appear stuck.
- Dense persistence creates large edge payloads and many entity-label writes. Splitting very large,
  entity-dense documents into coherent episodes reduces peak payload and retry cost.
- Increasing FalkorDB `TIMEOUT` hides symptoms but does not fix the pathological query plan.

## Operational Guidance

1. Keep the PR #1711 compatibility patch until an upstream release contains it.
2. Pin FalkorDB instead of using `latest`; this repository pins the tested manifest digest.
3. Ingest episodes sequentially per graph group and keep `SEMAPHORE_LIMIT` conservative.
4. Split documents that extract dozens of entities or facts into logical episodes.
5. Monitor `GRAPH.SLOWLOG <graph>` before increasing database timeouts.
6. For large warm graphs, evaluate a FalkorDB vector-index patch or Neo4j rather than relying on
   exhaustive vector scans.
