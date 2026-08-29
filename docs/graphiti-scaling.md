# Graphiti Performance and Scaling Guide

Verified against the repository, the running local stack, and public sources on
`2026-08-22`.

## Executive Conclusion

Graphiti is a viable candidate for asynchronous agent memory on FalkorDB, but the current
deployment is not yet production-qualified. The measured cold-graph result is encouraging:
one 1,400-token episode produced 11 entities and 12 facts in 16.4 seconds, while five hybrid
fact searches had 324 ms median and a 351 ms maximum (reported as p95 by the benchmark). This is
one bounded local run, not a capacity benchmark.

Three conditions dominate the scaling decision:

1. Keep the local Graphiti PR #1711 patch. Without it, FalkorDB relationship full-text searches
   can perform an entity-label scan for every hit and turn ingestion into minutes or timeouts.
2. Measure warm graphs. FalkorDB vector similarity in `graphiti-core==0.29.3` scans stored entity
   or edge embeddings; ingestion deduplication performs one entity similarity search per extracted
   entity. Empty-graph latency therefore cannot be projected unchanged to large graphs.
3. Serialize updates within a `group_id`, and gain concurrency across isolated groups with
   separate Graphiti clients and bounded workers. `SEMAPHORE_LIMIT=5` is a conservative starting point,
   not a demonstrated optimum.

Use `add_episode` for normal incremental, temporal memory. Evaluate `add_episode_bulk` only for
bounded imports after correctness tests against the pinned source. Chunk entity-dense documents
before Graphiti. Keep communities out of the online write path unless their retrieval value has
been demonstrated.

Managed Zep performance statements are not OSS Graphiti expectations. Zep uses a proprietary
Context Graph Engine and a managed retrieval stack; its advertised sub-200 ms retrieval and
million-graph positioning do not predict `graphiti-core` plus FalkorDB performance.

## Scope and Version State

The findings apply to this repository's current stack:

| Component | Current state |
|---|---|
| Graphiti | `graphiti-core==0.29.3` |
| Graphiti MCP source | Commit `993e081a6d7948a0d8851c12a5fbdbeb49fed862` |
| FalkorDB | Image digest `sha256:adbddd418916c25618564ff8597a919b08bc76452ebeb74eb985c38d7281df62`; live module version `42004` (`4.20.4`) |
| Extraction model | `gpt-5.6-luna` for the current deployment and benchmark |
| Embeddings | `text-embedding-3-small`, 1,536 dimensions |
| Concurrency | `SEMAPHORE_LIMIT=5` |
| Compatibility change | Local, idempotent application of Graphiti PR #1711 |

As of `2026-08-22`, `v0.29.3` is the latest stable GitHub and PyPI release. It was published on
`2026-07-27`. PR #1711 is open, unmerged, and absent from `v0.29.3`; the repository applies its
FalkorDB query rewrite at startup through `scripts/patch_graphiti.py`. Recheck both facts before
any Graphiti upgrade and remove the patch only after the released source contains the fix.

This guide consolidates conclusions. See [FalkorDB Performance Notes](falkordb-performance.md)
for the query plan, patch implementation, and micro-reproduction, and
[Graphiti Cost and Volume Benchmark](../reports/graphiti-cost-20260821T230704Z.md) for token,
cost, and projection detail.

## Evidence Boundaries

| Statement | Status | Basis |
|---|---|---|
| PR #1711 removes the per-hit endpoint label scan | Documented and locally reproduced | Upstream PR/source plus local before/after query test |
| A 1,400-token cold episode took 16.4 seconds | Measured once | Repository benchmark on a new isolated graph |
| Search was 324 ms median and 351 ms maximum | Measured over five queries | Same local benchmark; the report labels the maximum p95, but five samples are too few for a production percentile |
| Low and high episodes take about 5.5 and 51.3 seconds | Estimated | Linear/complexity extrapolations from the measured medium episode |
| Warm ingestion and vector search worsen as a graph grows | Documented mechanism; magnitude unmeasured | Pinned FalkorDB queries compute cosine similarity over matched entities or edges |
| More cross-group workers increase throughput | Engineering inference | Independent physical graphs permit parallel work, subject to shared provider, CPU, memory, and I/O limits |
| Sequential same-group writes preserve the best temporal context | Upstream recommendation | `add_episode` retrieves recent episodes and may invalidate prior facts |
| Bulk ingestion is faster | Upstream claim, not locally measured | Public adding-episodes guide; pinned implementation still requires local benchmarking |
| Current tuning is production-safe | Not established | No warm, concurrent, soak, failover, or restore benchmark has passed |

Treat all unmeasured bands and SLOs below as planning hypotheses. Do not use the historical public
Graphiti issue #467, the Zep paper, or managed Zep marketing as a substitute for this stack's tests.

## Ingestion Pipeline

For `add_episode`, elapsed time is the sum of network-bound model work and graph work. In
`v0.29.3`, the important stages are:

1. Validate the group and retrieve recent episodes for temporal and extraction context.
2. Extract entities with a structured-output LLM request.
3. Embed extracted entity names, search existing entity embeddings, and resolve duplicates.
   Ambiguous candidates can add an LLM deduplication request.
4. Extract facts/relationships with an LLM request.
5. Embed and search fact candidates, deduplicate facts, identify contradictions, and extract
   temporal validity. Candidate-dependent LLM work can appear on warm graphs.
6. Extract custom attributes. The local benchmark made three attribute calls for 11 entities;
   calls depend on entity types and extracted data.
7. Update entity summaries and embeddings.
8. Persist the episode, mentions, entities, facts, invalidations, temporal fields, and provenance.
9. Optionally update communities, adding graph queries, embeddings, and LLM summarization.

The measured medium episode used five LLM calls total: one entity extraction, one edge extraction,
and three attribute extraction calls. It made 28 embedding requests covering 70 texts. That call
shape is descriptive only. Warm deduplication candidates, a different ontology, retries, or
communities can add work.

## Latency and Throughput Bands

### Local baseline

| Workload | Basis | Episode latency | Sequential rate |
|---|---|---:|---:|
| Low, about 350 source tokens | Extrapolated | 5.47 s | 11.0 episodes/minute |
| Mid, about 1,400 source tokens | Measured once | 16.41 s | 3.7 episodes/minute |
| High, about 3,500 source tokens | Extrapolated with complexity buffer | 51.28 s | 1.2 episodes/minute |

The rates are `60 / latency`, not load-test throughput. They assume one sequential worker, no
queueing, no retries, an empty graph, and content similar to the benchmark. The corresponding
ideal five-worker ceilings would be 54.8, 18.3, and 5.9 episodes/minute only if scaling were
perfect. They are mathematical ceilings, not expected production rates; provider limits and one
FalkorDB instance make perfect scaling unlikely. The report did not capture a portable hardware
profile, so even single-operation latency must be rebaselined in the target environment.

For MCP-equivalent edge hybrid RRF search, the cold local baseline was 324 ms median and 351 ms
maximum across five queries returning up to ten facts. It used one query embedding and no LLM
reranker. This is latency, not measured concurrent QPS.

### Cold versus warm graphs

Cold graphs avoid most candidate resolution. Warm graphs add work in two dimensions:

- **Per-episode history:** recent episodes increase prompt context and can expose duplicates or
  contradictions that require resolution.
- **Graph cardinality:** FalkorDB node and edge similarity queries in `v0.29.3` match all eligible
  entities or relationships, calculate cosine similarity, sort, and limit. No Graphiti-created
  FalkorDB vector index is used by these query paths.

If an episode extracts `E` entities from a group containing `N` entities, entity candidate lookup
does approximately `E` similarity scans over that group's eligible entities. This supports an
`O(E * N)` database-work model for that stage, but constant factors and end-to-end latency must be
measured. Fact search similarly scans eligible `RELATES_TO` edges for cosine search. Full-text BM25
uses FalkorDB indexes, but PR #1711 is required to avoid the separate endpoint-resolution
pathology.

Expected production behavior is therefore a latency curve, not a fixed number. Benchmark at
representative warm cardinalities and stop extrapolating the cold bands once candidate searches
appear in the slowlog or stage traces.

## Bottlenecks and Failure Modes

| Bottleneck | Effect | Control |
|---|---|---|
| Unpatched FalkorDB edge full-text endpoints | Per-hit entity scans, multi-second queries, ingestion timeout | Keep PR #1711 patch; verify after upgrades |
| Exhaustive vector similarity | Warm ingestion and search grow with graph cardinality | Partition groups; measure a vector-index patch or another backend |
| LLM extraction and resolution | Seconds of latency, variable tokens, rate limits, malformed structured output | Queue writes, bound concurrency, retry with jitter, record prompt-level usage |
| Entity/fact density | More searches, embeddings, LLM candidates, and larger writes than token count alone suggests | Split at semantic boundaries; load-test by extracted counts |
| Dense persistence payloads | CPU, memory, network, and transaction spikes | Bound episode and bulk sizes; monitor query memory and slowlog |
| Excess concurrency | Provider `429`s, FalkorDB queueing, memory spikes, tail-latency collapse | Start at five global operations; tune from saturation tests |
| Cancellation | Client task cancellation does not guarantee already queued FalkorDB work stops immediately | Avoid repeated abort/retry loops; inspect server queue and slowlog |
| Communities on each write | Extra graph traversal and LLM summarization per entity | Build offline; update only when retrieval benefit pays for it |
| Single hot group | One graph cannot be split across FalkorDB cluster shards | Redesign partition boundary or evaluate another backend |

Raising a timeout masks slow plans and increases queue residence. Fix the plan first, then set a
bounded timeout that accommodates valid p99 work.

## `add_episode` versus `add_episode_bulk`

Use `add_episode` by default. It is the clearest incremental path, retrieves recent context,
resolves against the live graph, persists invalidations, and is explicitly documented upstream as
a sequential background operation.

`add_episode_bulk` parallelizes extraction and batches persistence, but has different operational
risk:

- The public adding-episodes page says bulk is for empty graphs or cases where edge invalidation is
  unnecessary. That warning is stale relative to the pinned `v0.29.3` implementation.
- The `v0.29.3` source passes bulk edges through `resolve_extracted_edges` and persists returned
  invalidated edges. However, its in-memory `dedupe_edges_bulk` phase says it does not track edge
  invalidation. Do not infer complete semantic parity without a contradiction test suite.
- The implementation saves episode nodes before extraction and final graph persistence. A failed
  batch can therefore leave partial episode state. Use stable UUIDs, reconciliation, and a durable
  job ledger.
- Bulk deduplication compares entities and edges within the batch and against the live graph. Its
  source notes quadratic in-memory node work as batch entities grow and identifies ten as a typical
  chunk size, but `add_episode_bulk` does not enforce that size.
- Bulk does not update communities and has not been benchmarked in this repository.

Start bulk evaluation at 5-10 episodes per call. Compare facts, invalidations, provenance, partial
failure recovery, peak memory, provider calls, and elapsed time against sequential `add_episode`
before increasing the batch. The public documentation and pinned source must both be reviewed on
every upgrade.

## Episode Chunking

An episode is a provenance and temporal unit, not merely a token chunk. Prefer one coherent event,
conversation segment, file section, or structured record set per episode.

Practical starting rules:

- Keep content within the extraction model's context limit, including recent-episode and ontology
  prompt overhead.
- Use about 1,000-3,000 source tokens as an initial test range, not a hard limit. The local 1,400
  token case is measured; the 3,500 token case is only extrapolated.
- Split earlier when content contains dozens of named entities or facts, large JSON arrays, many
  unrelated sections, or produces large persistence payloads.
- Preserve semantic and temporal boundaries. Carry minimal explicit context into the next episode
  instead of broad overlap that can duplicate facts.
- Give every chunk a deterministic source ID, chunk index, reference time, and stable UUID so it
  can be retried and reconciled.
- Ingest related chunks in reference-time order within the group.

`v0.29.3` contains density-aware utilities with defaults such as a 3,000-token target and 200-token
overlap, but neither `add_episode` nor `add_episode_bulk` calls those utilities. Automatic Graphiti
chunking must not be assumed. If this repository adopts the utilities, first test duplicate facts,
cross-boundary relationships, temporal invalidation, and provenance.

## Group Partitioning and Concurrency

With FalkorDB, Graphiti maps a `group_id` to a physical FalkorDB graph. Partition on a boundary
that owns coherent history, such as tenant, user, project, or bounded workspace.

- Keep all facts that require joint deduplication, contradiction handling, and search in one group.
- Do not create tiny groups solely to hide vector-scan cost if queries need cross-group context.
- Serialize ingestion per group. Parallel same-group writes can read the same previous state and
  race on deduplication, summaries, and invalidations.
- Run different groups concurrently through separate Graphiti/client instances. In `v0.29.3`,
  selecting another group can replace the instance's driver, so sharing one instance across
  concurrent group calls is unsafe by inspection.
- Apply a keyed queue or lock: concurrency one for each group, with a global worker/provider limit
  initially set to five.
- Set `SEMAPHORE_LIMIT` before importing Graphiti. The pinned module-level default is 20, while
  current upstream README prose says 10; this repository explicitly uses 5. Many internal
  `semaphore_gather` calls use the module value unless a caller passes `max_coroutines`.
- Increase in steps `1, 2, 3, 5` only while provider errors, FalkorDB queue depth, memory, and p95
  latency remain healthy.

FalkorDB Cluster distributes different graph keys across shards; it does not split one graph.
Clustering can scale many groups, not one hot group. Confirm Graphiti driver/client cluster support
before adopting it rather than assuming a standalone connection follows cluster redirects.

## Search Choices

| Need | Recipe | Tradeoff |
|---|---|---|
| Default factual memory | `EDGE_HYBRID_SEARCH_RRF` / current MCP fact search | BM25 plus cosine, one query embedding, no reranker LLM; best first choice |
| Entity overview | `NODE_HYBRID_SEARCH_RRF` | Searches names and returns summaries; node vector scan grows with entities |
| Context near a known entity | Edge or node hybrid with node-distance reranking | Useful structural bias; requires a valid center node and graph traversal |
| Diverse context | MMR recipe | Reduces redundant results; tune lambda and validate relevance |
| Highest relevance on a small candidate set | Cross-encoder recipe | Adds model latency/cost and, in stock recipes, BFS candidate work |
| Broad themes | Community search | Requires expensive community construction and potentially stale summaries |
| Exact provenance | Episode BM25 or fact results followed by episode lookup | Avoids pretending entity summaries are source evidence |

Keep queries short and specific, filter to the smallest group and result scope, and request only the
needed result count. Begin with edge hybrid RRF. Add node distance, MMR, or a cross-encoder only
after an offline retrieval-quality set shows a material gain. Record candidate count and reranker
latency separately.

Communities are optional derived data. In pinned source, building them loads group entities,
queries neighbors per entity, runs label propagation, and summarizes clusters with multiple LLM
calls. Build them asynchronously after bulk loads, rebuild periodically if used, and do not include
their cost in baseline search or ingestion expectations. The public communities page says Leiden,
but the pinned `v0.29.3` implementation shown above is label propagation; use pinned source as the
authority for this deployment.

## FalkorDB Settings

### Live local state

The running pinned container reported the following on `2026-08-22`:

| Setting | Live value | Interpretation |
|---|---:|---|
| `THREAD_COUNT` | 12 | Maximum concurrent FalkorDB queries |
| `OMP_THREAD_COUNT` | 12 | Potential per-query GraphBLAS parallelism |
| `CACHE_SIZE` | 25 | Cached query plans |
| `ASYNC_DELETE` | On | Graph deletion runs asynchronously |
| `MAX_QUEUED_QUERIES` | 25 | Bounded pending-query queue |
| `TIMEOUT` | 1,000 ms | Deprecated legacy timeout; it caused the local slow read to fail fast |
| `TIMEOUT_DEFAULT` / `TIMEOUT_MAX` | 0 / 0 | Modern timeout controls are not configured |
| `RESULTSET_SIZE` | 10,000 | Global result cap |
| `QUERY_MEM_CAPACITY` | 0 | No per-query memory cap |
| `DELTA_MAX_PENDING_CHANGES` | 10,000 | Pending graph-change bound |
| `NODE_CREATION_BUFFER` | 16,384 | Matrix growth allocation |
| `VKEY_MAX_ENTITY_COUNT` | 100,000 | Entities represented per replication virtual key |
| `CMD_INFO` / `MAX_INFO_QUERIES` | On / 1,000 | FalkorDB query telemetry is enabled and bounded |
| `EFFECTS_THRESHOLD` | 0 | Replication-effect threshold reported by the live module |
| `DELAY_INDEXING` | Off | Indexes are built during graph decoding |
| `JS_HEAP_SIZE` / `JS_STACK_SIZE` | 256 MiB / 1 MiB | JavaScript UDF limits; not a Graphiti hot path |
| `IMPORT_FOLDER` / `TEMP_FOLDER` | `/var/lib/FalkorDB/import/` / `/tmp` | CSV import and temporary-operation paths |
| Redis `maxmemory` | 0 | No Redis memory limit |
| Redis eviction | `noeviction` | Graph keys are not evicted under a configured memory limit |
| RDB `save` | `3600 1 300 100 60 10000` | Snapshot schedule |
| AOF | Off | Writes since the last successful RDB snapshot can be lost on failure |
| RDB file/data path | `dump.rdb` in `/var/lib/falkordb/data` | Mounted to named volume `falkordb-data` |

The Docker volume provides restart persistence, not backup, high availability, or a bounded RPO.

### Production tuning

Apply settings at image/module startup and keep them in version control; runtime `GRAPH.CONFIG SET`
changes do not survive restart.

1. Use the pinned `falkordb/falkordb-server` production image without the browser. Keep the digest,
   module version, CPU, memory, and storage class fixed for each benchmark.
2. Replace deprecated `TIMEOUT` with measured `TIMEOUT_DEFAULT` and `TIMEOUT_MAX`. Start evaluation
   around a 30-second default and 120-second maximum after PR #1711, then set values from p99 valid
   reads and writes. Timeouts are guards, not tuning fixes, and a timed-out write is rolled back.
3. Tune `THREAD_COUNT` to allocated CPU and workload. Test a low `OMP_THREAD_COUNT` such as 1-2
   when many queries run concurrently to avoid CPU oversubscription; retain higher values only if
   single-query wins outweigh tail-latency loss.
4. Keep `MAX_QUEUED_QUERIES` finite. Test roughly 2-4 times `THREAD_COUNT`, rejecting excess work at
   the application queue instead of accumulating an unbounded database backlog.
5. Raise `CACHE_SIZE` only if metrics show plan churn across repeated Graphiti query shapes; it is
   a plan-cache count, not a result cache.
6. Set `QUERY_MEM_CAPACITY` and `RESULTSET_SIZE` from observed production-shaped peaks. Graphiti
   normally requests small result sets, so a very large global result cap is unnecessary.
7. Reserve memory headroom for FalkorDB matrices, query working sets, RDB copy-on-write, and the OS.
   Use `noeviction`; an evicted graph key is data loss. Alert before the host or container OOMs.
8. Benchmark `NODE_CREATION_BUFFER` and `DELTA_MAX_PENDING_CHANGES` only for write-heavy bulk loads.
   Larger values trade memory for fewer resizes or larger transactions.
9. Enable authentication, private networking, encryption appropriate to the deployment, and
   least-privilege access. Do not place credentials in compose files, logs, traces, or this guide.

All numeric production values above are starting experiments, not universal recommendations.

## Durability and Observability

### Durability

- Use AOF with `appendfsync everysec` plus RDB snapshots for a provisional one-second database RPO;
  test the actual latency and recovery cost. Use `always` only if its write penalty is acceptable.
- Store data on durable storage and copy verified RDB/AOF backups off-host. Schedule restore drills.
- Add one or more replicas for redundancy and read capacity if the client path supports it. FalkorDB
  replication is asynchronous, so replicas do not provide zero-RPO durability or automatic
  read-after-write consistency.
- Use Sentinel, FalkorDB Cluster, or an equivalent orchestrated failover mechanism if automatic
  promotion is required; a standalone primary plus replica is not automatic failover by itself.
- Keep the source episode or event in a durable queue/object store. The graph is a derived index
  that must be rebuildable.
- Track job states `accepted`, `running`, `committed`, and `failed`; retry by stable episode UUID and
  reconcile partial bulk writes before acknowledging success.

### Observability

Collect at least:

- End-to-end ingestion latency, queue wait, attempts, outcome, group, source tokens, extracted
  entities/facts, invalidations, and persisted payload size.
- Stage latency for previous-context retrieval, entity extraction, node candidate search, edge
  extraction/resolution, attributes/summaries, embeddings, persistence, and communities.
- Provider requests, tokens, cost, `429`s, timeouts, retry-after, malformed output, and retry count.
- Search latency by recipe/scope, candidate count, result count, reranker latency, and a sampled
  retrieval-quality score.
- FalkorDB query latency, errors, timeouts, queue rejections, CPU, RSS, memory headroom, disk I/O,
  persistence status, replication lag, and backup age.
- Queue depth and age by group, active groups, worker utilization, dead-letter count, and freshness.

`graphiti-core v0.29.3` accepts an OpenTelemetry tracer and emits top-level ingestion, LLM, and
search spans with useful counts. Export those spans and add application queue/persistence spans.
Its token tracker is suitable for process-level accounting. `GRAPH.SLOWLOG <graph>` retains only
up to ten queries of at least 10 ms, so poll/export it; it is a diagnostic, not a complete metrics
store. Redact episode content, prompts, search text, credentials, and sensitive entity attributes.

## Production Architecture

Use an asynchronous write path and an independently scalable read path:

```text
clients
  |-- search API/MCP --> stateless search workers --> FalkorDB read path
  `-- ingest API -----> durable queue keyed by group_id
                              |
                         ingestion workers
                         one active job/group
                         global limit initially 5
                              |
                         LLM + embeddings
                              |
                         FalkorDB primary
                              |
                    AOF/RDB + replica + backups
```

- Return an ingestion job ID quickly; do not hold a user request open for 5-50 seconds.
- Preserve per-group order in the queue while allowing independent groups to occupy workers.
- Use separate Graphiti instances for concurrent groups and separate search and ingestion process
  pools so backfills cannot consume all interactive capacity.
- Route read-after-write requests to the primary. Use replicas only after acceptable lag and driver
  routing are demonstrated.
- Schedule communities, large imports, backup work, and consistency checks away from peak search.
- For many independent groups, evaluate FalkorDB Cluster because it places different graph keys on
  different shards. For one large hot graph, a cluster does not solve the cardinality problem.

## Load-Test Methodology

Every test must pin Graphiti, the patch hash, FalkorDB digest/settings, model, embedding dimensions,
ontology, hardware, provider tier, and dataset seed. Save raw per-operation results, not only
averages.

### Phase 0: Correctness and instrumentation

- Build indexes, verify the PR #1711 query is active, and assert no old query remains.
- Create golden episodes for duplicates, contradictions, changing dates, retries, chunk boundaries,
  and bulk partial failure.
- Verify facts, temporal fields, provenance, stable UUID retry behavior, and restart persistence.
- Confirm traces, token counts, slowlog export, and resource metrics contain no secrets.

### Phase 1: Single-operation baselines

- Run low, mid, high, sparse, and entity-dense profiles at least 30 times on isolated cold graphs.
- Measure every ingestion stage and the edge RRF, node RRF, node-distance, cross-encoder, and
  community recipes separately.
- Repeat the PR #1711 micro-test and persistence-payload test from
  [FalkorDB Performance Notes](falkordb-performance.md).

### Phase 2: Warm growth curves

- Preload representative groups at increasing entity/edge cardinalities, for example 1k, 10k,
  50k, and 100k, while keeping degree and duplicate rates realistic.
- At each point, run new-entity, duplicate-heavy, contradiction-heavy, and dense episodes plus a
  fixed retrieval-quality query set.
- Plot p50/p95/p99 latency and candidate-stage database time against entities and edges. Record the
  cardinality where SLO or cost growth becomes unacceptable.

### Phase 3: Concurrency and mixed traffic

- Test global concurrency `1, 2, 3, 5` across independent groups with one worker per group.
- Run same-group concurrency as a correctness stress test, not a proposed production mode.
- Mix interactive search with steady ingestion and backfill. Increase offered load until queue age,
  provider throttling, database queueing, memory, or search p95 breaks its gate.
- Compare sequential `add_episode` with bulk sizes `5` and `10`; increase only after correctness and
  memory gates pass.

### Phase 4: Soak and recovery

- Run 24-72 hours with production-shaped arrivals, retries, provider faults, and periodic backups.
- Restart workers and FalkorDB during writes; verify idempotency and recovery from partial bulk state.
- Exercise replica/failover behavior, restore an off-host backup into a clean environment, and
  measure RPO/RTO.

## Provisional SLOs

These are initial acceptance targets, not achieved service levels:

| Indicator | Provisional target |
|---|---:|
| Ingest API acceptance p95 | <= 250 ms, returning a durable job ID |
| Mid episode completion p95, excluding queue wait | <= 30 s |
| High/dense episode completion p95 | <= 90 s or route to an explicit backfill class |
| Ingestion success after bounded retries | >= 99% |
| Mid-episode freshness p95 at planned load | <= 60 s from acceptance to searchable |
| Edge hybrid RRF search p95 | <= 750 ms |
| Edge hybrid RRF search p99 | <= 1.5 s |
| Single-worker mid throughput | >= 3 completed episodes/minute |
| Three independent-group workers | >= 8 completed mid episodes/minute while search p95 passes |
| Database RPO | <= 1 s with tested AOF/replication configuration |
| Restore RTO | <= 30 minutes for the qualified graph size |

Define availability only after failure handling and a deployment topology exist. Measure retrieval
quality beside latency; a fast search that misses required facts does not pass.

## Decision Gates

1. **Patch gate:** Do not deploy FalkorDB without PR #1711 behavior. Block an upgrade if the patch
   fails to apply and released source still has the old query.
2. **Correctness gate:** `add_episode`, retries, and any bulk path must pass duplicate,
   contradiction, temporal, provenance, and partial-failure tests.
3. **Warm-scale gate:** The largest expected group must meet search and ingestion SLOs at steady
   state, not only when empty.
4. **Concurrency gate:** Increase above five only when provider errors, FalkorDB queueing, memory,
   cost, and p95/p99 all remain within budget.
5. **Partition gate:** Use FalkorDB Cluster only when load consists of many independent groups and
   client compatibility is proven. It cannot rescue one hot graph.
6. **Vector gate:** If warm vector scans dominate before required cardinality, implement and test a
   FalkorDB vector-index query path or evaluate Neo4j/another backend. Do not compensate only with
   timeouts or smaller result limits.
7. **Bulk gate:** Adopt bulk only if it materially improves throughput and exactly passes the
   temporal/correctness and recovery suite at the chosen batch size.
8. **Community gate:** Enable communities only when an offline retrieval evaluation shows enough
   quality gain to justify build latency, LLM cost, storage, and staleness.
9. **Durability gate:** No production launch until backup restore, restart during write, replication
   lag, and stated RPO/RTO are tested.
10. **Build-versus-buy gate:** If the required operational SLA, multi-tenant scale, or retrieval
    latency cannot be met economically, evaluate managed Zep or another managed service. Rebenchmark
    it directly; managed Zep metrics are not OSS Graphiti baselines.

## Sources

Repository evidence:

- `docs/falkordb-performance.md`
- `reports/graphiti-cost-20260821T230704Z.md`
- `reports/graphiti-cost-20260821T230704Z.json`
- `docker-compose.yaml`
- `config/graphiti-mcp.yaml`
- `scripts/patch_graphiti.py`
- `src/agent_graph_memory/compat.py`

Public sources, verified `2026-08-22`:

- Graphiti `v0.29.3` release: https://github.com/getzep/graphiti/releases/tag/v0.29.3
- Graphiti `0.29.3` on PyPI: https://pypi.org/project/graphiti-core/0.29.3/
- Graphiti PR #1711: https://github.com/getzep/graphiti/pull/1711
- Graphiti `v0.29.3` ingestion implementation: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/graphiti.py
- Graphiti `v0.29.3` concurrency defaults: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/helpers.py
- Graphiti `v0.29.3` bulk implementation: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/utils/bulk_utils.py
- Graphiti `v0.29.3` FalkorDB search operations: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/driver/falkordb/operations/search_ops.py
- Graphiti `v0.29.3` search recipes: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/search/search_config_recipes.py
- Graphiti `v0.29.3` chunking utilities: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/utils/content_chunking.py
- Graphiti `v0.29.3` community operations: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/utils/maintenance/community_operations.py
- Graphiti `v0.29.3` tracing implementation: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/tracer.py
- Graphiti adding episodes: https://help.getzep.com/graphiti/core-concepts/adding-episodes.md
- Graphiti communities: https://help.getzep.com/graphiti/graphiti/communities.md
- Graphiti README comparison of OSS and managed Zep: https://github.com/getzep/graphiti/blob/v0.29.3/README.md
- FalkorDB configuration: https://docs.falkordb.com/getting-started/configuration
- FalkorDB durability: https://docs.falkordb.com/operations/durability/index
- FalkorDB Docker persistence: https://docs.falkordb.com/operations/durability/persistence
- FalkorDB replication: https://docs.falkordb.com/operations/replication
- FalkorDB Cluster behavior: https://docs.falkordb.com/operations/cluster
- FalkorDB slowlog: https://docs.falkordb.com/commands/graph.slowlog
- OpenTelemetry Python instrumentation: https://opentelemetry.io/docs/languages/python/instrumentation/
- Historical Graphiti cost issue #467: https://github.com/getzep/graphiti/issues/467
- Zep temporal knowledge graph paper: https://arxiv.org/abs/2501.13956
- OpenAI API pricing: https://developers.openai.com/api/docs/pricing
