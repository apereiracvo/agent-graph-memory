# FalkorDB vs. Neo4j as Graphiti Backends

Last reviewed: 2026-08-22

## Executive Decision

Keep FalkorDB for this repository's current small, single-group deployment, but treat that as a
conditional decision rather than a general Graphiti recommendation.

The current deployment should retain all of these safeguards:

- Keep the local [Graphiti PR #1711](https://github.com/getzep/graphiti/pull/1711) compatibility
  patch until an upstream release contains the fix.
- Use one `Graphiti` client per group, or serialize mutations across groups. Do not concurrently
  mutate different `group_id` values through one shared FalkorDB-backed client while
  [issue #1676](https://github.com/getzep/graphiti/issues/1676) remains unresolved.
- Pin and smoke-test the complete Python dependency set, not only `graphiti-core`.
- Enable AOF as well as snapshots before treating the current self-hosted service as durable.
- Verify that every accepted episode appears in the graph; the MCP queue can acknowledge work and
  later discard a failed episode ([issue #1707](https://github.com/getzep/graphiti/issues/1707)).

Re-evaluate Neo4j before any of the following:

- a single group grows into the 10,000-100,000 entity range and warm-graph ingestion or semantic
  retrieval no longer meets its service-level objective;
- database-level concurrent writes to one graph become important for workloads other than
  Graphiti's ordered per-group episode stream;
- point-in-time correctness, multi-query atomicity, online backup, mature RBAC, or supported HA is
  required;
- the team no longer wants to own Graphiti-specific FalkorDB patches and routing tests.

For genuinely high volume, the answer depends on topology. Neo4j Enterprise or Aura is the safer
default for one large shared graph. FalkorDB becomes competitive for thousands of independent,
moderate-size tenant graphs because it can place different graph keys on different cluster shards,
but it cannot split one large graph across those shards. That architecture is acceptable only after
the Graphiti FalkorDB routing defects are fixed or isolated by application design.

## Scope and Evidence

This comparison is about the code paths Graphiti actually uses, not the complete feature list of
either database. It was prepared against:

- `graphiti-core==0.29.3`, released as
  [v0.29.3](https://github.com/getzep/graphiti/releases/tag/v0.29.3);
- Graphiti MCP commit `993e081a6d7948a0d8851c12a5fbdbeb49fed862`;
- this repository's pinned FalkorDB image and PR #1711 patch;
- local measurements in [FalkorDB Performance Notes](falkordb-performance.md) and the
  [cost benchmark](../reports/graphiti-cost-20260821T230704Z.md);
- official product documentation and public Graphiti issues.

The direct comparative evidence is limited. There is no representative independent benchmark of
the same Graphiti ingestion and retrieval workload on current FalkorDB and Neo4j releases. Vendor
benchmarks are useful for generating hypotheses, not for making this decision by themselves.

## What Graphiti Exercises

Graphiti ingestion is not a simple graph insert. For each episode it can perform LLM extraction,
embedding, entity and fact candidate searches, LLM deduplication, contradiction handling, and a
series of graph writes. Retrieval can combine full-text, exhaustive cosine similarity, graph
traversal, temporal filters, and reciprocal-rank fusion.

Three consequences dominate the backend comparison:

1. **Graphiti does not use native vector ANN on either backend.** In 0.29.3, it creates range and
   full-text indexes only. Semantic searches filter with `MATCH`, calculate cosine similarity for
   each candidate, sort, and limit. Both databases offer native vector indexes, but those product
   capabilities do not improve unmodified Graphiti. [Issue #1055](https://github.com/getzep/graphiti/issues/1055)
   tracks the missing index use. Any ANN replacement must preserve tenant-local results; global ANN
   followed by `group_id` filtering can return too few candidates from the requested tenant.
2. **Normal ingestion is a sequence of independent statements.** The Neo4j driver exposes a real
   transaction context with commit and rollback, whereas FalkorDB provides atomicity per query and
   serializes writes per graph. Graphiti's normal ingestion path does not wrap the complete episode
   mutation in the Neo4j transaction context, so a backend switch alone does not make an episode
   atomic.
3. **LLM latency can hide database differences until the graph is warm.** The local empty-graph
   medium episode took 16.4 seconds and five LLM calls. A Neo4j user reported about one hour for
   100 bulk records with `SEMAPHORE_LIMIT=1` in
   [issue #1262](https://github.com/getzep/graphiti/issues/1262). Database scaling should therefore
   be measured separately from extraction time as well as end to end.

## Architecture Comparison

| Area | FalkorDB with Graphiti | Neo4j with Graphiti | Practical effect |
|---|---|---|---|
| Tenant layout | Graphiti maps each `group_id` to a physical FalkorDB graph key | Groups normally share one database and are filtered by `group_id` | FalkorDB gives strong physical separation and small search domains, but routing is more complex |
| Storage model | In-memory-first sparse matrices with Redis persistence | Disk-backed native graph store with configurable page cache and JVM heap | FalkorDB capacity is closely tied to RAM; Neo4j can retain a graph larger than RAM with a latency cost |
| Read concurrency | Parallel snapshot reads on a graph | Concurrent ACID read transactions | Both support concurrent reads; benchmark the exact hybrid recipe |
| Write concurrency | One write query at a time per physical graph | Concurrent transactions with locking and deadlock handling | Neo4j has stronger database-level concurrency, but Graphiti live episodes should still remain ordered within a group |
| Atomicity | One Cypher query is atomic; no native multi-query Graphiti transaction | Full multi-query ACID transactions are available | Graphiti currently leaves partial-episode risk on both; Neo4j offers a path to improve it |
| Full-text | RediSearch-backed node and relationship indexes | Lucene-backed node and relationship indexes | Both are used by Graphiti; FalkorDB needs PR #1711 for safe edge endpoint resolution at scale |
| Vector search | HNSW vector indexes exist, but Graphiti does not create or query them | Lucene vector indexes exist, but Graphiti does not create or query them | Current Graphiti semantic work grows with the filtered candidate set on both |
| Single-graph scale-out | A graph is one Redis key and remains on one shard | Enterprise clusters replicate a database; Infinigraph is the separately licensed sharding option | Ordinary FalkorDB Cluster scales across graphs, not within one graph |
| Multi-graph scale-out | Redis Cluster distributes separate graph keys among masters | Enterprise supports multiple databases and federation; Community is single-database | FalkorDB topology aligns naturally with many independent Graphiti groups |
| Durability | RDB, AOF, or both; replication is asynchronous | Transaction logs and ACID commits; supported online backup is Enterprise | Current RDB-only FalkorDB config has a wider recovery-point window |
| HA | Self-managed replication/cluster is possible; managed HA starts in Cloud Pro | Clustering is Enterprise; Aura Business Critical provides multi-zone HA | Neither free single-node edition supplies production HA |
| Security | Redis ACLs and TLS; verify graph-key restrictions against the exact deployment | Community has basic users; fine-grained RBAC, subgraph controls, LDAP/OIDC, and security logging are Enterprise features | Neo4j Enterprise is materially stronger for regulated deployments |
| Operations | Small footprint, Redis tooling, graph slowlog and memory commands | Mature query logs, metrics, memory tooling, backup, clustering, and driver routing | Neo4j has the broader production operations surface, mostly paid |
| License | FalkorDB core is SSPLv1; external database-as-a-service use needs legal review or a commercial license | Neo4j Community is GPLv3; Enterprise and Aura are commercial | Review the actual distribution/service model with counsel |

FalkorDB's concurrency guarantees are documented in
[Atomicity and Concurrency](https://docs.falkordb.com/design/concurrency). Neo4j transaction behavior
is documented in its [Python driver manual](https://neo4j.com/docs/python-manual/current/transactions/).

## Graphiti Integration Risk

FalkorDB is a supported Graphiti backend, but the current adapter has a larger correctness and
compatibility risk surface than the Neo4j path.

| Item | Status on the reviewed version | Consequence or mitigation |
|---|---|---|
| [PR #1711](https://github.com/getzep/graphiti/pull/1711) / [issue #1592](https://github.com/getzep/graphiti/issues/1592) | Open; locally reproduced and patched | Without the patch, broad relationship full-text hits can cause one entity scan per hit and make ingestion time out |
| [Issue #1676](https://github.com/getzep/graphiti/issues/1676) | Open | Shared-driver mutation can silently write concurrent groups into the wrong physical graph; isolate clients or serialize cross-group mutation |
| [Issue #1651](https://github.com/getzep/graphiti/issues/1651) | Open | MCP `get_episodes` and `delete_episode` can use the currently bound graph rather than the intended group; test these operations directly |
| [Issue #1625](https://github.com/getzep/graphiti/issues/1625) | Open report | FalkorDB point-in-time episode retrieval may admit future episodes; block temporal-SLA use until reproduced against the pinned stack and fixed |
| [Issue #1756](https://github.com/getzep/graphiti/issues/1756) | Open dependency report | A clean FalkorDB extra can resolve an incompatible `redis` version; lock the full environment and run driver construction in CI |
| [Issue #1325](https://github.com/getzep/graphiti/issues/1325) | Original routing defect addressed in v0.29.3 | Keep single- and multi-group retrieval regression tests because related handler paths remain problematic |
| [Issue #1643](https://github.com/getzep/graphiti/issues/1643) | The untracked-task defect was addressed by PR #1636 in v0.29.3 | Initialization is now tracked, but constructors still schedule index work; explicitly await index creation before serving traffic |

Issue state is not proof that every report applies to every server/client combination. The table
separates the locally reproduced PR #1711 defect from issue-based risks that still need pinned-stack
regression tests.

Neo4j avoids FalkorDB's per-group physical routing class of bugs because `group_id` is normally a
property filter in one database. It is not risk-free: exhaustive semantic search still scales with
the selected group, normal Graphiti ingestion still uses separate statements, and the asynchronous
MCP acknowledgement problem is backend-independent.

## Measured Local Result

The repository reproduced the relationship full-text bottleneck with 500 entities, 1,000 matching
`RELATES_TO` edges, and a limit of 50:

| Query | Result |
|---|---:|
| Graphiti 0.29.3 endpoint pattern | Exceeded FalkorDB's 1-second query timeout |
| PR #1711 direct `startNode`/`endNode` lookup | 6.5 ms for 50 rows |

This establishes that the patch is mandatory for the current FalkorDB deployment. It does not
establish that patched FalkorDB is faster than Neo4j for Graphiti overall.

FalkorDB publishes a
[Neo4j comparison benchmark](https://benchmark.falkordb.com/), but its synthetic expansion,
vertex, and write operations do not model Graphiti's extraction, tenant filtering, full-text/vector
fusion, temporal predicates, deduplication, or many-statement ingestion. The publisher is also one
of the compared vendors. Do not use its headline latency ratio for capacity planning.

## Decision Matrix

Scores are 1 (poor) to 5 (strong) for this repository's Graphiti use, not for general-purpose graph
database use. Asterisked rows depend substantially on paid editions or managed tiers.

| Criterion | Weight | FalkorDB | Neo4j | Reason |
|---|---:|---:|---:|---|
| Current repository fit and migration cost | 15 | 5 | 2 | FalkorDB is already deployed, pinned, patched, and measured |
| Graphiti adapter maturity/correctness | 20 | 2 | 4 | Current FalkorDB routing and query defects are operationally significant |
| Many-tenant physical isolation | 10 | 5 | 3 | One Falkor graph per group is a natural isolation and sharding unit |
| One-group database write concurrency | 10 | 2 | 4 | FalkorDB serializes writes per graph; Neo4j supports concurrent transactions, although Graphiti live episodes remain ordered |
| Current Graphiti semantic-search scaling | 10 | 3 | 3 | Both use filtered exhaustive cosine scoring rather than native ANN |
| Durability, backup, and HA* | 15 | 3 | 5 | Neo4j Enterprise/Aura has stronger integrated guarantees and tooling |
| Security and governance* | 10 | 3 | 5 | Neo4j Enterprise has richer RBAC, auth integration, and audit controls |
| Operational simplicity at small scale | 5 | 5 | 3 | FalkorDB is lightweight and already part of the stack |
| Ecosystem and diagnostics | 5 | 3 | 5 | Neo4j has a broader mature tool and operations ecosystem |
| **Weighted total** | **100** | **330/500** | **375/500** | Neo4j leads for a new production selection; migration cost keeps FalkorDB rational now |

The total should not override topology. Raising the weight of current fit and tenant isolation favors
FalkorDB; raising correctness, write concurrency, security, or HA favors Neo4j.

## Recommendations by Scale

### Current Scale

Use FalkorDB and avoid migration now. The measured workload is small, the current integration is
already operational, and Graphiti's LLM work is likely to dominate before database infrastructure
does. Migrating now would add implementation and validation cost without evidence of a user-visible
gain.

Before calling it production-ready:

- retain PR #1711 and add an upgrade test that fails when the patch is no longer applicable;
- use a fixed group per client, which this repository's `graphiti_client()` currently does;
- enable AOF `everysec` in addition to RDB, establish off-host backups, and run restore drills;
- enforce a memory limit and `noeviction`; never let a graph database evict keys for memory pressure;
- record queue job state or synchronously verify episode persistence;
- test add, search, retrieve, and delete for two groups both sequentially and concurrently;
- monitor `GRAPH.SLOWLOG`, queue depth, timeout count, memory by graph, and recovery-point age.

### 10,000-100,000 Entities per Group

Run the benchmark below before choosing. This size is not inherently large for either database, but
it is where Graphiti's exhaustive candidate scoring and warm-graph deduplication can become more
important than empty-graph ingestion measurements.

Prefer Neo4j if this is one or a few shared groups, non-Graphiti writes need database-level
concurrency, or operational assurance
matters more than minimum footprint. Prefer FalkorDB if groups remain independent, each graph fits
comfortably in RAM, writes can be serialized per group, and patched Graphiti meets measured p95 and
p99 targets.

Do not assume native vector indexes solve this band. Using them requires a Graphiti search-interface
implementation and a tenant-filtering design. Test recall as well as latency, because global ANN
followed by `group_id` filtering can return too few tenant-local candidates.

### Genuinely High Volume

Define high volume in workload terms: entities and edges per group, number of groups, writes per
second per group, hybrid queries per second, embedding dimensions, retention, and recovery targets.

- **One very large graph:** shortlist Neo4j Enterprise/Aura first. Ordinary Neo4j clustering gives
  replicated primaries and read secondaries; sharding requires the separately licensed Infinigraph
  offering. Validate storage, page-cache hit rate, exhaustive semantic scans, and cost.
- **Many independent moderate graphs:** shortlist FalkorDB Cluster. Different graph keys can land on
  different masters, so aggregate throughput can scale with groups. A single graph remains on one
  shard, and each graph's writes remain serialized.
- **Strict multi-tenant ANN:** consider implementing Graphiti's `SearchInterface` against a search
  engine or a backend/version that supports selective vector filtering. Preserve exact `group_id`
  isolation and compare retrieval recall against exhaustive scoring.
- **Strict no-loss or regulated operation:** use a supported paid topology, tested backup/restore,
  observable job completion, and explicit ingestion idempotency. Neither a single OSS node nor the
  current MCP queue is enough.

## Commercial and Operational Boundaries

Open-source feature comparisons can be misleading because the production features are packaged
differently.

- FalkorDB core is SSPLv1 and supports RDB/AOF, asynchronous replication, Redis Cluster, ACLs, and
  graph diagnostics. The official [license FAQ](https://docs.falkordb.com/references/license) says
  internal use does not require releasing application code but offering FalkorDB as a service may.
- [FalkorDB Cloud Startup](https://docs.falkordb.com/cloud/tiers/startup) starts at $73/month for 1 GB
  and includes TLS and 12-hour backups, but not HA, clustering, or continuous persistence.
- [FalkorDB Cloud Pro](https://docs.falkordb.com/cloud/tiers/pro) starts around $350/month for its
  listed 2-core/8-GB standalone size and adds cluster deployment, HA, multi-zone operation,
  continuous persistence, and 24/7 support. Actual replicated configurations cost more.
- Neo4j Community is GPLv3, single-instance, and includes ACID transactions, full-text, and vector
  indexing. It excludes autonomous clustering, hot backup, multi-database, and advanced security.
- [Neo4j pricing](https://neo4j.com/pricing/) lists AuraDB Professional from about $65.70/month for
  1 GB, with a single-zone deployment and daily backups. AuraDB Business Critical starts at 2 GB,
  about $292/month, and adds a three-zone cluster, 99.95% SLA, stronger security, and 24/7 support.
- Neo4j self-managed clustering, online backup, fine-grained RBAC, and advanced operations are
  Enterprise features. Infinigraph sharding is a separate edition.

Prices and packaging change. Recheck them with required RAM, replicas, regions, support, network,
and backup retention at procurement time.

## Fair Benchmark Protocol

The benchmark must hold Graphiti, model output, embeddings, data, and client behavior constant. A
raw Cypher microbenchmark is useful for diagnosis but cannot answer the backend decision.

### 1. Freeze the Test Artifact

- Use the same `graphiti-core` commit for both drivers.
- Apply only provider-specific fixes that would be deployed, and report patched and unpatched
  FalkorDB separately where useful.
- Record database server, Python driver, Redis client, Python, OS, CPU, RAM, disk, and configuration
  versions.
- Give both databases the same hardware budget. Report resident memory and disk separately rather
  than forcing identical internal memory layouts.

### 2. Eliminate LLM Variance

- Run one canonical extraction and embedding pass, save the structured entities, facts, UUIDs,
  timestamps, and vectors, and replay those identical artifacts into each backend.
- Also run an end-to-end pass with the same cached LLM responses to measure Graphiti orchestration.
- Use deterministic UUIDs and timestamps so graph contents and retrieval outputs can be diffed.
- Test low-, medium-, and high-entity episodes, including contradictions and duplicate entities.

### 3. Test Representative Topologies

- Single group at 1k, 10k, 100k, and 1m entities, with realistic edge density.
- 100 and 1,000 groups with equal total data, plus a skewed distribution where one group owns most
  data.
- Cold cache after restart and warm steady state.
- FalkorDB standalone and, when relevant, cluster with graph keys deliberately distributed across
  shards; Neo4j single node and the paid topology actually under consideration.

### 4. Measure Workloads Separately

Ingestion:

- episodes/minute and database-only write time;
- p50/p95/p99 end-to-end episode completion;
- queries, bytes, and LLM/embedding calls per episode;
- warm-graph deduplication time as graph size increases;
- partial-state and duplicate counts after injected retries.

Retrieval:

- full-text node and edge search;
- exhaustive node and edge semantic search;
- Graphiti's actual hybrid RRF recipe;
- one- to three-hop BFS and temporal filtering;
- p50/p95/p99 latency, throughput, timeout/error rate, and result equivalence;
- recall@k and nDCG@k against a fixed relevance set if an ANN implementation is evaluated.

Concurrency:

- 1, 5, 20, and 50 readers on one group;
- 1, 2, 5, and 10 writers on one group;
- the same writers distributed over many groups;
- mixed read/write traffic and noisy-neighbor tenant skew.

### 5. Inject Failures

- Kill the database during each ingestion phase and after acknowledgement but before completion.
- Restart during index creation, snapshot/AOF activity, and high query load.
- Fail over the paid HA topology and measure write loss, rejection window, recovery time, and stale
  reads.
- Exhaust memory and disk in a controlled environment; verify `noeviction` and explicit failures.
- Restore backups to a new environment and compare node, edge, index, UUID, group, and temporal
  invariants.
- Concurrently mutate two FalkorDB groups and audit every UUID's physical graph to catch #1676.

### 6. Report Costs and Pass/Fail Gates

Report database infrastructure, operations labor, support/license, LLM, embedding, retry, and backup
cost separately. LLM cost is backend-independent only if retries and candidate counts remain equal.

Set gates before running, for example:

- no missing, duplicate, cross-group, or temporally invalid records;
- zero acknowledged-but-unobservable episode failures;
- p95 ingestion and hybrid retrieval within the product SLO;
- recovery point and recovery time within the agreed RPO/RTO;
- at least 30 minutes of steady state after warm-up, repeated three times;
- no comparison result based solely on vendor-provided synthetic workloads.

## Migration Considerations

Changing the Graphiti driver is a manageable application change, but moving existing data safely is
not only a connection-string change.

FalkorDB stores each group in a separate physical graph. A normal Neo4j Graphiti deployment stores
those groups together and relies on `group_id` properties and indexes. Migration must therefore:

1. inventory all FalkorDB graph keys and map each one to its expected `group_id`;
2. export nodes, relationships, labels/types, UUIDs, embeddings, episode lists, and temporal fields;
3. normalize provider-specific values, especially ISO datetime strings and vector representations;
4. import idempotently into a new Neo4j database without changing UUIDs or edge direction;
5. run Graphiti index/constraint creation and wait for indexes to become online;
6. compare counts and per-group UUID sets, then replay a golden retrieval suite;
7. dual-write or pause ingestion for the final delta, cut over, and retain a tested rollback window.

Replaying source episodes through Graphiti is simpler semantically but changes extracted output as
models and prompts evolve, consumes LLM tokens, and may not preserve UUIDs or contradiction history.
A direct model-preserving migration is preferable when historical identity matters; episode replay
is preferable when the source corpus is authoritative and rebuilding is acceptable.

Before migration work, add a backend factory instead of replacing the FalkorDB import in
`src/agent_graph_memory/graph.py` inline. Keep one backend active per process during validation, and
do not add compatibility abstractions until both deployment configurations are concrete.

## Source Index

- Graphiti release and issues: [v0.29.3](https://github.com/getzep/graphiti/releases/tag/v0.29.3),
  [#1055](https://github.com/getzep/graphiti/issues/1055),
  [#1262](https://github.com/getzep/graphiti/issues/1262),
  [#1325](https://github.com/getzep/graphiti/issues/1325),
  [#1592](https://github.com/getzep/graphiti/issues/1592),
  [#1625](https://github.com/getzep/graphiti/issues/1625),
  [#1643](https://github.com/getzep/graphiti/issues/1643),
  [#1651](https://github.com/getzep/graphiti/issues/1651),
  [#1676](https://github.com/getzep/graphiti/issues/1676),
  [#1707](https://github.com/getzep/graphiti/issues/1707), and
  [#1756](https://github.com/getzep/graphiti/issues/1756).
- FalkorDB: [concurrency](https://docs.falkordb.com/design/concurrency),
  [durability](https://docs.falkordb.com/operations/durability),
  [replication](https://docs.falkordb.com/operations/replication),
  [cluster topology](https://docs.falkordb.com/operations/cluster),
  [index types](https://docs.falkordb.com/cypher/indexing), and
  [vector indexes](https://docs.falkordb.com/cypher/indexing/vector-index).
- Neo4j: [cluster architecture](https://neo4j.com/docs/operations-manual/current/clustering/introduction/),
  [backup editions](https://neo4j.com/docs/operations-manual/current/backup-restore/),
  [memory model](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/),
  [vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/),
  [authentication and authorization](https://neo4j.com/docs/operations-manual/current/authentication-authorization/),
  and [pricing/edition matrix](https://neo4j.com/pricing/).
