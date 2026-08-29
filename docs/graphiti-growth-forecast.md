# Graphiti Growth Forecast

Reviewed against `graphiti-core==0.29.3`, repository source analysis, public sources, and the
measured FalkorDB report generated on 2026-08-26.

## Executive Answer

For a fixed-size episode, API tokens and API cost should not rise linearly with the total graph.
Graphiti sends only recent history and bounded search candidates to its LLM prompts. A mature graph
can make candidate-dependent deduplication, contradiction, timestamp, and attribute calls happen
more often, so tokens per episode can step up from the cold baseline, but the prompt does not contain
all `N` entities or all `R` stored facts. Plan API cost as a mostly flat per-episode band controlled by
episode density and candidate-hit rate, not as `O(N)` token growth.

Database time is different. In Graphiti 0.29.3 on FalkorDB, node and relationship cosine searches
calculate similarity across the eligible graph because Graphiti does not create or call FalkorDB's
HNSW vector indexes. The measured p50 rose from 1.697 to 19.794 ms for a node scan as `N` went from
100 to 10,000, and from 2.615 to 379.699 ms for the benchmark's edge hybrid operation as `R` went
from 150 to 15,000. Thus ingestion gradually changes from API-bound to database-bound as a single
group grows. Retrieval follows the same edge-scan curve.

Using the medium episode observed here, `E=11`, `F=12`, concurrency five, and the fitted database
curves, the estimated database critical-path addition is about 0.09-0.16 s after 100 episodes,
0.96-1.85 s after 1,000, 4.84-9.37 s after 5,000, and 9.69-18.77 s after 10,000. The upper bound
conservatively treats the endpoint-constrained fact duplicate search like a graph-wide scan. Adding
the 16.41 s cold API/application calibration gives approximately 16.50-16.57, 17.37-18.26,
21.25-25.78, and 26.10-35.18 s for the next medium episode. The 5,000 and 10,000 episode values are
long extrapolations, not measurements.

The planning implication is simple:

- Up to roughly 1,000 medium episodes in one group, API latency and cost remain the primary concern.
- Around 1,000-2,500 episodes, watch edge hybrid p50 and warm-ingestion spans closely.
- Beyond the measured range, require a warm end-to-end test before approving capacity. Do not solve
  scan growth only by increasing timeouts.
- API spend remains approximately linear in episode count unless mature-graph candidate behavior or
  retries change the per-episode band. Database latency is the nonlinear cumulative risk.

This is a capacity forecast, not a service guarantee. A claim of 60-80% planning accuracy, if used,
applies mostly to p50 database timing while interpolating within or near the measured range. It does
not apply to p95/p99, end-to-end ingestion, provider latency, concurrent load, or the far 5,000 and
10,000 episode extrapolations.

## Plain-Language Summary

Three different quantities affect ingestion in different ways:

1. **The new episode's size and density** determine most LLM work. More source tokens, extracted
   entities, extracted facts, typed attributes, and temporal changes produce larger prompts or more
   calls.
2. **Existing entity count** affects entity deduplication. Graphiti runs a semantic lookup for every
   entity extracted from the new episode. With the current FalkorDB path, each lookup compares
   against the eligible stored entities.
3. **Existing relationship/fact count** affects fact deduplication, contradiction detection, and
   user fact search. The current semantic path compares against eligible stored `RELATES_TO` edges.

Relationship growth is the larger measured scaling risk in this setup. In the synthetic benchmark,
the fitted node scan added about `0.00184 ms` per stored entity, while edge hybrid search added about
`0.0253 ms` per stored fact. That is roughly 14 times more latency per stored fact than per stored
entity for these exact queries, data, and hardware. A medium episode also produced similar numbers
of new entities and facts, 11 and 12, so stored facts dominate the projected database curve.

The content pattern changes what happens:

| Incoming pattern | Expected effect |
|---|---|
| Mostly known entities and duplicate facts | Stored `N` and `R` grow slowly, so database scan growth can flatten; candidate-resolution LLM calls may still occur |
| Known entities but many new relationships | Entity growth slows, but `R` keeps growing; this remains the main ingestion and retrieval scaling risk |
| Many new entities but few relationships | Node deduplication grows with `N`, but the measured node path is much cheaper than the edge path |
| Many new entities and relationships | Both paths grow; this is the conservative projection used in this report |
| Contradictions and changing facts | Old facts are invalidated rather than deleted, so historical `R` and memory continue growing |

Entity domains often do saturate, but relationship history may not. The same bounded set of people,
projects, products, or systems can accumulate many facts, updates, and temporal versions. For that
reason, a stable entity set does not guarantee stable Graphiti performance.

API token usage follows a different pattern. Graphiti does not send the entire graph to the LLM. It
sends bounded candidate sets: at most 15 candidates per unresolved entity and approximately 10
duplicate plus 10 invalidation candidates per fact. A larger graph makes it more likely that those
slots are populated and that deduplication or contradiction calls run, but it does not make prompt
tokens increase in direct proportion to `N` or `R`. For a fixed episode shape, expect token cost to
rise from a cold level toward a mature-graph band and then tend to plateau. It can continue rising if
episodes themselves become larger or denser, history episodes are larger, more typed attributes are
extracted, communities are enabled, or retries increase.

The numerical growth curve in this report is not copied from an official Graphiti capacity
benchmark. No representative public benchmark was found that controls episode shape and measures
tokens and latency across increasing warm graph cardinalities. The conclusions combine:

- pinned Graphiti 0.29.3 source, which establishes the bounded LLM candidates and exhaustive
  FalkorDB cosine query shapes;
- this repository's zero-API benchmark, which measures those database paths from 100/150 to
  10,000/15,000 entities/facts;
- public Graphiti issue and PR measurements, which confirm severe warm-graph full-text and vector
  bottlenecks in other deployments;
- one external production observation reporting 39% more input tokens in a mature graph than in a
  fresh graph.

Public reports validate the mechanisms and warning signs, while the local benchmark supplies the
consistent size-to-latency curve used for the projections. Managed Zep's sub-200 ms retrieval claims
use a proprietary indexed engine and are not an OSS Graphiti/FalkorDB baseline.

## Symbols and Scope

| Symbol | Definition |
|---|---|
| `S` | Source tokens in the episode body before Graphiti prompt overhead |
| `E` | Entity nodes extracted from the episode before resolution |
| `F` | Facts/`RELATES_TO` edges extracted from the episode before resolution |
| `N` | Stored `Entity` nodes in the target group immediately before ingestion |
| `R` | Stored `RELATES_TO` edges in the target group immediately before ingestion |
| `D` | Estimated FalkorDB hot-path wall time added to one ingestion, excluding API and application time |

The forecast applies to one FalkorDB physical graph selected by one Graphiti `group_id`. FalkorDB
maps groups to graph keys, so aggregate scale across many independent groups is a different problem.
The model covers normal `add_episode`, communities disabled, 1,536-dimensional embeddings, the local
PR #1711 relationship endpoint patch, and the edge hybrid RRF retrieval used by this repository.

Graphiti invalidation is temporal, not physical deletion. Invalidated facts receive `invalid_at` and
`expired_at` values and remain stored for history and provenance. Therefore they continue to count in
`R`, consume memory, and can affect scans unless query filters exclude them. A contradiction-heavy
graph can grow faster than its number of currently valid facts.

## Evidence Classes

| Label | Meaning in this report |
|---|---|
| **Measured** | Direct local value in a linked JSON/Markdown report |
| **Source-derived** | Behavior read from pinned Graphiti 0.29.3 source |
| **Estimate** | Formula using measured inputs and explicit assumptions |
| **Long extrapolation** | Formula evaluated materially beyond `N<=10,000` and `R<=15,000` |
| **Public observation** | A reported case, not independently reproduced in this repository |

## Exact Graphiti 0.29.3 Ingestion Pipeline

The relevant `add_episode` path is:

1. Validate ontology and group. If the requested FalkorDB group differs, clone/select a driver for
   that physical graph.
2. Retrieve at most 10 recent episodes (`RELEVANT_SCHEMA_LIMIT=10`) at or before the reference time.
   Normal `add_episode` explicitly uses 10 even though the lower-level general episode-window default
   is three. Supplying `previous_episode_uuids` replaces this lookup.
3. Extract entities in one structured LLM request. For this repository's `EpisodeType.text`, the
   selected prompt contains `S`, source description, ontology descriptions, and custom instructions,
   but not the recent episodes. Message prompts do include prior messages. `add_episode` does not
   automatically invoke the density-aware chunking utilities.
4. Collapse exact same-episode names, batch-embed extracted names, and run one node cosine candidate
   search per extracted entity. Each search returns at most 15 candidates above 0.6, but its FalkorDB
   query computes cosine similarity over all eligible `N` entities.
5. Resolve obvious matches deterministically. If unresolved candidates remain, send one batched node
   deduplication LLM request. Its existing-entity list is bounded by at most 15 candidates per
   unresolved extracted entity before UUID deduplication.
6. Extract facts in one structured LLM request. The prompt contains the resolved entity list, current
   episode, recent episodes, ontology, and temporal reference. The source sets an edge extraction
   output ceiling of 16,384 tokens, still subject to the provider/model context limit.
7. Batch-embed facts. For each fact, read edges between its resolved endpoint pair, run a duplicate
   edge hybrid search constrained to those UUIDs, and run a separate graph-wide hybrid search for
   invalidation candidates. Each `EDGE_HYBRID_SEARCH_RRF` call returns 10 final candidates; its BM25
   and cosine methods each request up to 20 before RRF. The cosine branch still scans eligible `R`.
8. Run one fact resolution LLM call per fact only when duplicate or invalidation candidates exist.
   Exact fact matches can short-circuit. For a new fact without timestamps, timestamp extraction can
   add a small-model call. Custom edge attributes can add another call.
9. Extract custom entity attributes per typed entity when the Pydantic type has fields. Entity
   summaries are batched in flights of at most 30 when summarization is required; short summaries can
   instead append new facts without an LLM call. The local ontology caused three attribute calls.
10. Regenerate required embeddings and persist the episode, mentions, resolved entities, facts,
    duplicate provenance, invalidated edges, temporal fields, and source provenance.
11. If `update_communities=True`, update each affected community with additional graph, embedding,
    and LLM work. Communities are disabled in this forecast.

Other exact limits relevant to planning are `DEFAULT_SEARCH_LIMIT=10`, `MAX_SEARCH_DEPTH=3`, a
128-space-delimited-term full-text query budget, 1,000-character persisted entity/community
summaries, and a
module-level `SEMAPHORE_LIMIT` default of 20. This repository uses five. `Graphiti(max_coroutines=5)`
is not honored by every nested gather, so `SEMAPHORE_LIMIT=5` must be loaded before Graphiti imports.
The local LLM benchmark configured 4,096 output tokens, while the edge extraction function can pass
its more specific 16,384 ceiling.

`add_episode_bulk` is not included. Its source and public documentation are not fully aligned on edge
invalidation, it can leave partial episode state, and it has not been measured here. Use normal,
ordered `add_episode` for this forecast.

## Bounded Prompts, Unbounded Scans

This distinction explains why API tokens and database time have different growth curves.

| Work | Bound reaching the LLM | Database work before the bound |
|---|---|---|
| Recent episode context | At most 10 episodes | Indexed/order-limited episode lookup |
| Entity resolution | At most 15 candidates per unresolved extracted entity | One exhaustive cosine calculation over eligible `N` per `E` |
| Fact duplicate prompt | At most 10 final hybrid candidates | Endpoint lookup plus BM25 and cosine work; cosine can scan eligible filtered edges |
| Fact invalidation prompt | At most 10 final hybrid candidates | Global BM25 and exhaustive cosine over eligible `R` per `F` |
| User edge RRF retrieval | At most 10 final results by default | BM25 plus exhaustive cosine over eligible `R` |

The top-k `LIMIT` constrains returned candidates and prompt size; it does not make a query that
calculates and sorts cosine similarity over all matching nodes or edges an ANN query. FalkorDB has
HNSW node and relationship indexes, but Graphiti 0.29.3 neither creates nor queries them on this path.

API usage can nevertheless rise with graph maturity. Empty graphs skip candidate LLM resolution.
Warm graphs increase the probability of a bounded candidate list, contradictions, timestamp work,
summary refresh, and retries. The number and size of those calls depend on content, not merely `N` or
`R`. That candidate-hit probability is the largest unmeasured cost variable.

## Local Cold Calibration

**Measured once on a new isolated graph:** one representative medium text episode using
`gpt-5.6-luna`, `text-embedding-3-small`, six custom entity types, and FalkorDB.

| Metric | Measured value |
|---|---:|
| Source | 8,412 characters, about 1,400 tokens |
| Extracted entities/facts | 11 / 12 |
| LLM requests | 5: one entity, one fact, three custom attributes |
| LLM input/output tokens | 13,240 / 1,017 |
| Total LLM tokens | 14,257 |
| Embedding requests/texts/tokens | 28 / 70 / 428 |
| End-to-end ingestion | 16.41 s |
| Standard API ingestion cost at recorded prices | $0.00387696 |
| Five cold edge RRF searches | 323.8 ms median, 351.0 ms maximum |
| Search API work | One embedding, no reranker LLM, about $0.000000164/query |

The provider Admin API reconciled exactly five Luna requests, 13,240 input tokens, and 1,017 output
tokens. Embedding tokens were locally counted. Five search samples cannot establish p95; the old
report field named `p95` is the maximum of five.

This calibration contains API, orchestration, local database, and network time. It is not a warm
capacity result and has no portable hardware profile. The separate hot-path benchmark below is the
source of database growth, not the 324 ms Python end-to-end cold search.

## Measured FalkorDB Growth

**Measured:** isolated synthetic graph, Graphiti-compatible schema and query text, patched
relationship endpoints, 1,536 dimensions, eight deterministic vector prototypes, `R=1.5N`, result
limit 20, two warmups, seven samples, 30 s query timeout, six FalkorDB threads, and one OpenMP thread.
The host was Apple arm64 with FalkorDB running in Linux Docker. There were zero OpenAI calls.

| `N` | `R` | Graph MB | Redis used MB | Node cosine p50/max ms | Edge cosine p50/max ms | Typical FT hits/p50 ms | Broad FT hits/p50 ms | Edge hybrid p50/max ms |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 150 | 1 | 5.82 | 1.697 / 2.048 | 2.197 / 2.670 | 8 / 0.544 | 150 / 0.648 | 2.615 / 2.709 |
| 500 | 750 | 8 | 13.92 | 2.443 / 2.610 | 7.269 / 7.879 | 38 / 0.608 | 750 / 1.097 | 7.900 / 8.416 |
| 1,000 | 1,500 | 16 | 24.05 | 3.207 / 3.523 | 24.073 / 24.707 | 75 / 0.632 | 1,500 / 1.602 | 24.375 / 24.747 |
| 2,500 | 3,750 | 41 | 55.10 | 6.016 / 6.129 | 97.944 / 118.012 | 188 / 0.854 | 3,750 / 3.171 | 117.102 / 118.869 |
| 5,000 | 7,500 | 81 | 105.95 | 10.757 / 10.868 | 158.328 / 190.618 | 375 / 0.930 | 7,500 / 5.983 | 160.750 / 192.858 |
| 10,000 | 15,000 | 163 | 207.82 | 19.794 / 20.079 | 361.738 / 447.765 | 750 / 1.238 | 15,000 / 11.744 | 379.699 / 448.655 |

`Graph MB` is FalkorDB's sampled graph-memory report. `Redis used MB` converts bytes to decimal MB
and includes server/process overhead, including a 2.91 MB measured empty baseline. Synthetic repeated
vectors and text are useful for operation count and scaling shape, not a realistic recall or memory
distribution. The exact benchmark graph was deleted and its absence verified.

## Fitted Formulas

Ordinary least-squares fits to the six p50 points are below. Clamp negative predictions to zero.
Units are milliseconds and decimal MB as noted.

```text
node cosine:       tN(N) =  1.478 + 0.001835 * N       R2=0.9999
edge cosine:       tR(R) = -7.172 + 0.024244 * R       R2=0.9940
edge hybrid:       tH(R) = -5.244 + 0.025267 * R       R2=0.9859
broad edge FT:     tB(R) =  0.475 + 0.0007467 * R      R2=0.9996
graph memory:      MG(N) = -0.307 + 0.016327 * N MB   R2=1.0000, only at R=1.5N
Redis used memory: MR(N) =  3.801 + 0.020412 * N MB   R2=1.0000, only at R=1.5N
```

High `R2` describes these six synthetic medians; it does not establish causal linearity, tail
behavior, realistic embeddings, or validity beyond the tested interval. The hybrid benchmark ran
its BM25 and cosine components sequentially, while Graphiti normally gathers them concurrently.
Using `tH` in ingestion projections is therefore conservative for one unloaded search.

The 2,500-entity point also shows real noise: edge cosine was 97.944 ms while compound edge hybrid
was 117.102 ms, then the gap narrowed at 5,000. Prefer ranges and decision gates over false precision.

## Conversion Assumptions

The medium projection deliberately keeps all conversions explicit.

| Conversion | Base assumption | Status and consequence |
|---|---:|---|
| Source per episode | `S=1,400` tokens, 8,412 ASCII bytes | Measured once; about 175,000 source tokens/MiB |
| Entities per episode | `E=11` | Measured extraction; projection assumes all remain unique, so `N(K)=11K` |
| Facts per episode | `F=12` | Measured extraction; projection assumes all add stored edges, so `R(K)=12K` |
| LLM amplification | 14,257 / 1,400 = 10.18 LLM tokens/source token | Measured cold prompt overhead, not a warm constant |
| Embedding amplification | 428 / 1,400 = 0.306 embedding tokens/source token | Measured cold ingestion |
| Source volume | 0.00802 MiB/episode | Raw episode body only, excluding JSONL metadata |
| Graph memory | About 0.180 reported MB/episode | Estimate from `11 * 0.016327`; conservative edge density is `R=1.5N`, not medium `12/11` |
| Redis memory | About 0.225 decimal MB/episode plus 3.80 MB | Estimate from `11 * 0.020412`; includes synthetic/server effects |

At 100/1,000/5,000/10,000 medium episodes, source volume is about 0.80/8.02/40.11/80.22
MiB, while the synthetic-ratio graph-memory fit gives about 17.7/179/898/1,795 reported MB. The
5,000 and 10,000 memory values are **long extrapolations**. Real duplicate resolution lowers `N` or
new-edge growth; invalidations remain stored and can raise `R`; real summaries, attributes, episode
nodes, mentions, index overhead, allocator behavior, and persistence can move memory substantially.

## Medium-Episode Projections

Let `K` be already-ingested medium episodes and use `N=11K`, `R=12K`. Graphiti runs `E` node scans
in a bounded gather, then two separate `F`-search fact stages. The duplicate stage is constrained to
edges between the resolved endpoint pair; the invalidation stage is graph-wide. With concurrency
`c=5`, use a range rather than blindly summing every measured scan:

```text
Dbase(K) = ceil(E/5) * tN(11K) + ceil(F/5) * tH(12K)
         = 3 * tN(11K) + 3 * tH(12K)

Dupper(K) = ceil(E/5) * tN(11K) + 2 * ceil(F/5) * tH(12K)
          = 3 * tN(11K) + 6 * tH(12K)

Dserial(K) = E * tN(11K) + 2F * tH(12K)
           = 11 * tN(11K) + 24 * tH(12K)
```

`Dbase` prices the one clearly graph-wide fact search per fact and leaves endpoint-local work outside
the cardinality curve. `Dupper` conservatively prices both fact stages as graph-wide. `Dserial` is a
database-work envelope, not expected elapsed time. None includes point lookups, writes, queueing, LLM
calls, embedding calls, retries, or competition from another request. Nested and phase-level
concurrency is more complex than these formulas.

| Existing medium episodes `K` | Projected `N` / `R` | `tN` / `tH` ms | `Dbase-Dupper` s | Cold 16.41 s + DB range | Serial scan envelope | Label |
|---:|---:|---:|---:|---:|---:|---|
| 100 | 1,100 / 1,200 | 3.50 / 25.08 | 0.09-0.16 | 16.50-16.57 s | 0.64 s | Estimate, interpolation |
| 1,000 | 11,000 / 12,000 | 21.66 / 297.96 | 0.96-1.85 | 17.37-18.26 s | 7.39 s | Estimate, near measured edge range; node slightly beyond |
| 5,000 | 55,000 / 60,000 | 102.39 / 1,510.79 | 4.84-9.37 | 21.25-25.78 s | 37.39 s | **Long extrapolation** |
| 10,000 | 110,000 / 120,000 | 203.31 / 3,026.83 | 9.69-18.77 | 26.10-35.18 s | 74.88 s | **Long extrapolation** |

The cold constant is held fixed only to expose database growth. Warm candidate LLM calls can raise
both token use and latency; database and API phases can also overlap differently from the simple sum.
At high concurrency, FalkorDB's six query threads, queue, CPU, and memory bandwidth can make even
`Dupper` optimistic despite its conservative per-hybrid input.

For one sequential group, summing the growing range gives estimated cumulative completion times of
0.46 h at 100, 4.69-4.81 h at 1,000, 26.15-29.28 h at 5,000, and 59.03-71.62 h at 10,000, including
the 16.41 s cold constant per episode. The last two are **long extrapolations**. Do not divide these
blindly by five: same-group episodes should remain ordered, and internal scan concurrency is already
represented. Concurrency across independent groups can reduce fleet wall time, subject to provider
and database saturation.

## Database Crossover

The crossover compares `Dbase-Dupper` with the 16.41 s cold API/application calibration. Solving the
fitted formulas gives a range:

| Database share of cold 16.41 s | Estimated medium episodes | Approximate `N` / `R` span | Confidence |
|---:|---:|---:|---|
| 10% (1.64 s) | about 887-1,703 | 9,760-18,730 / 10,640-20,440 | Near to modest extrapolation |
| 50% (8.21 s) | about 4,379-8,469 | 48,170-93,160 / 52,550-101,630 | **Long extrapolation** |
| 100% (16.41 s) | about 8,744-16,926 | 96,180-186,190 / 104,930-203,110 | **Long extrapolation** |

These are not universal thresholds. Lower concurrency, duplicate-heavy endpoint pairs, concurrent
traffic, larger `R/N`, more invalidated historical edges, or slower hardware move crossover earlier.
A vector-index implementation or smaller physical group moves it later.

## Retrieval Warning Thresholds

Edge RRF retrieval runs BM25 and an exhaustive edge cosine search. `tH` is a useful conservative p50
database proxy, not an end-to-end or tail predictor.

| Warning | Fitted p50 database proxy | Approximate `R` | Medium episodes at `12K` | Status |
|---|---:|---:|---:|---|
| Observe | 250 ms | 10,100 | 840 | Within measured range |
| Investigate | 500 ms | 20,000 | 1,670 | Modest extrapolation |
| SLO risk | 750 ms | 29,900 | 2,490 | **Long extrapolation**; equals provisional search p95 target only numerically |
| Redesign | 1,000 ms | 39,800 | 3,320 | **Long extrapolation** |

Alert on measured end-to-end p95/p99, not these fitted p50 values. Start investigation when the
edge cosine or hybrid span exceeds 250 ms p50, search p95 exceeds 750 ms, search p99 exceeds 1.5 s,
or the slowlog repeatedly contains Graphiti cosine queries. Also gate on retrieval quality; an ANN
change that is fast but loses required tenant-local facts does not pass.

## API Tokens and Cost as the Graph Matures

**Estimate:** fixed medium source shape, current Standard prices, no cache discount, no Batch/Flex
discount, no regional uplift, no communities, and no retries. The external bands apply this
repository's measured output/input and embedding/input ratios to the external fresh and mature input
token observations. They are cross-deployment planning bands, not statistical confidence intervals.

| Band | Input/output/embedding tokens | Cost/episode | Interpretation |
|---|---:|---:|---|
| Local cold | 13,240 / 1,017 / 428 | $0.003877 | Measured here; candidate resolution usually absent |
| External fresh | 28,750 / 2,208 / 929 | $0.008419 | External measured input; output and embeddings ratio-estimated |
| External mature | 40,070 / 3,078 / 1,295 | $0.011733 | External measured input, 39% above fresh; output and embeddings ratio-estimated |

| Episodes | Local-cold cumulative | External-fresh cumulative | External-mature cumulative |
|---:|---:|---:|---:|
| 100 | $0.39 | $0.84 | $1.17 |
| 1,000 | $3.88 | $8.42 | $11.73 |
| 5,000 | $19.38 | $42.10 | $58.67 |
| 10,000 | $38.77 | $84.19 | $117.33 |

Only the local-cold band is measured for this repository. The external fresh/mature input values are
real Graphiti observations from another deployment, but their episode shape, ontology, prompts, and
model differ. Their 39% fresh-to-mature increase is better evidence for the shape of a maturity
penalty than their absolute token counts are for this deployment. Actual warm cost should be modeled
from candidate-hit telemetry as soon as it exists.

At the recorded prices, output tokens dominate their count-adjusted contribution more than input
tokens, while embeddings are negligible. Retrieval under edge RRF remains approximately one short
query embedding and no reranker LLM, so API query cost stays tiny even while local database latency
grows. Cross-encoder recipes change that conclusion.

## Public Numerical Evidence

Public cases are useful tripwires and mechanism checks, not pooled benchmark samples.

| Source | Numerical case | Relevance and boundary |
|---|---|---|
| [AIOS production measurement #506](https://github.com/aiosbrain/aios-team-brain/pull/506) | 98 fresh episodes averaged 28,750 metered input tokens versus 40,070 in mature production, a 39% maturity penalty | Strongest public warm-versus-fresh token observation found; external application, prompts, model, and content differ, so it supports a bounded maturity penalty rather than our exact dollar bands |
| [AIOS production measurement #488](https://github.com/aiosbrain/aios-team-brain/pull/488) | Across 1,372 Graphiti LLM calls, node attributes were 768 calls and 65.6% of spend; node dedup was 42 calls/13.9% and edge dedup 477/7.8% | Supports the source-derived conclusion that typed attributes and candidate activation, not total graph cardinality directly, dominate API cost |
| [Graphiti PR #1711](https://github.com/getzep/graphiti/pull/1711) | 3,725 entities, 20,374 edges, 1,027 FT hits: 33,383 ms before and 1.6 ms after direct endpoint lookup; episode write about 12 min to 45 s | Strong direct FalkorDB/Graphiti mechanism evidence; different graph, version 0.29.2, and broad output |
| [PR #1711 independent reproduction](https://github.com/getzep/graphiti/pull/1711#issuecomment-5159693799) | 2,377 entities/3,439 edges: 57.39 s to 0.05 s; 1,008/992: 0.35 s to near 0 | Strong independent confirmation of the unpatched pathology, not vector-scan performance |
| [Local PR #1711 reproduction](falkordb-performance.md#local-reproduction) | 500 entities, 1,000 matching edges, limit 50: old query exceeded 1 s; patched query 6.5 ms | Directly reproduced in this stack; establishes patch necessity |
| [Graphiti issue #1262](https://github.com/getzep/graphiti/issues/1262) | 100 bulk records took about 60 min, about 36 s/record; one 10-record batch 348,108 ms; edge resolution example 1,967 ms at semaphore one | Relevant API/dedup tripwire on Neo4j and v0.28.1; not a FalkorDB growth curve |
| [Graphiti issue #467](https://github.com/getzep/graphiti/issues/467) | About 40 chats of 150-250 words cost nearly $0.80, about $0.02/chat | Historical 2025 default-model observation before v0.27 prompt refactoring; workload and models differ |
| [Zep temporal KG paper](https://arxiv.org/abs/2501.13956) | LongMemEval average source context 115k tokens reduced to 1.6k retrieved tokens; latency 31.3 to 3.20 s for 4o-mini and 28.9 to 2.58 s for 4o | Strong retrieval-value case, but managed Zep/paper architecture is not OSS Graphiti plus FalkorDB ingestion evidence |
| [Zep paper DMR](https://arxiv.org/abs/2501.13956) | 500 conversations, five sessions, up to 12 messages/session; Zep 94.8% vs MemGPT 93.4% with GPT-4 Turbo | Retrieval-quality context only; authors note the conversations fit modern context windows |
| [FalkorDB vector docs](https://docs.falkordb.com/cypher/indexing/vector-index) | HNSW supports 1-4,096 dimensions; example capacity says 1M 768-float vectors need about 3 GB plus overhead | Shows an available redesign path; Graphiti 0.29.3 does not use it and docs warn property filtering is limited |

The Zep paper's quality and latency results must not be presented as this deployment's performance.
Managed Zep uses a separate production retrieval stack, and the paper does not report OSS Graphiti
ingestion cost as a function of graph cardinality.

## Observed Tripwires, Not Universal Limits

- **Measured:** patched edge hybrid reached 379.699 ms p50 and 448.655 ms max at 15,000 synthetic
  edges. This is a warning point, not a maximum supported edge count.
- **Measured:** sampled graph memory was 163 MB and Redis used memory 207.82 MB at 10,000 entities
  and 15,000 synthetic edges. This is not a production bytes-per-fact guarantee.
- **Measured:** the old relationship endpoint pattern timed out above 1 s at only 500 entities and
  1,000 matching edges; patched was 6.5 ms. That is a query-plan defect, not FalkorDB capacity.
- **Observed locally before patch:** dense full-text searches took 10-14 s and a nearly 1 MB dense
  edge-write payload took about 10 s. Entity-dense episode payloads deserve a separate gate.
- **Measured once:** medium cold ingestion was 16.41 s. Low/high source projections of 5.47/51.28 s
  and all warm values remain estimates.
- **Configured:** a 30 s query timeout, six database threads, one OpenMP thread, and queue size 25
  bounded the hot-path run. Different settings and concurrent work change tails.
- **Source-derived:** invalidated edges remain in the graph. There is no tested retention point at
  which historical edges become unsafe; memory and retrieval SLOs determine that point.

## Unknowns Ranked by Impact

1. **Warm candidate-hit and LLM-call rates.** This controls whether API tokens remain near 14,257 or
   move toward the base/high bands and can add seconds per fact.
2. **Warm end-to-end critical path under real concurrency.** The forecast combines separate cold API
   and database microbenchmarks; no trace proves their simple sum or tail behavior.
3. **Real `N`, `R`, and invalidation growth per episode.** Duplicate entities reduce cardinality;
   contradiction history and retained invalidated edges increase stored `R`.
4. **Production p95/p99 and saturation.** Seven unloaded samples do not cover queueing, mixed reads
   and writes, provider throttling, memory bandwidth, persistence, or backup activity.
5. **Real memory density.** Synthetic text, eight repeated vectors, missing episode/mention growth,
   custom attributes, and allocator behavior limit bytes-per-episode accuracy.
6. **Far-curve shape.** `N=110,000` and `R=120,000` are 8-11 times beyond measured cardinality. CPU
   caches, matrix resizing, query memory, and timeouts can break linear p50 fits.
7. **Retrieval quality and ANN filtering.** HNSW could flatten scans but needs exact group isolation,
   current/invalid fact filtering, recall@k evaluation, and safe over-fetch behavior.
8. **Content distribution.** Source tokens alone do not predict `E`, `F`, endpoint degree, temporal
   ambiguity, malformed structured output, retries, or attribute calls.
9. **Bulk semantic parity and failure recovery.** Bulk is not qualified and should not be assumed to
   reduce cumulative time safely.

## Experiments to Improve Confidence

### Minimal paid experiment

Ingest 24 fixed, production-shaped medium episodes against preseeded graphs at approximately 0,
1,000, 5,000, and 10,000 entities: three novel episodes and three duplicate/contradiction-heavy
episodes per plateau. Capture prompt-level calls/tokens, candidates, `E/F`, invalidations, embeddings,
stage spans, total latency, and retries. At the measured low rate this is about $0.09 in API usage;
the high allowance is about $0.29, excluding failed retries. Repeat only the surprising plateau.

This single experiment estimates the highest-impact unknown: how candidate rate changes API tokens
and critical-path latency with graph maturity. Use stable inputs and UUIDs, delete only its isolated
graphs, and reconcile provider usage.

### Zero-API-cost experiments

- Rerun `benchmark-falkordb` with at least 30 samples and plateaus through 25,000 or 50,000, stopping
  on a predeclared timeout or memory gate. Record p50/p95/p99, CPU, RSS, slowlog, and queue depth.
- Replace the eight vector prototypes with a deterministic realistic distribution and realistic
  fact/name lengths; vary `R/N`, including retained invalidated-edge ratios of 0%, 25%, and 100%.
- Replay cached or mocked LLM/embedding outputs through the complete Graphiti pipeline to measure
  orchestration, reads, writes, payload size, and concurrency without provider cost.
- Run mixed traffic at one, two, three, and five internal operations plus independent-group workers.
  Do not run unordered same-group ingestion as a throughput solution.
- Implement an experimental FalkorDB node/relationship HNSW `SearchInterface`, then compare exact
  exhaustive results with ANN recall@10, current-fact filtering, and group isolation before timing it.
- Poll `GRAPH.SLOWLOG`, inspect query plans, and fail the test if the pre-PR #1711 endpoint pattern
  reappears after an upgrade.

## Planning Rules and Decision Gates

1. Budget a medium episode at 16.41 s plus measured warm database `D`, not at a graph-independent
   16.41 s. Replace the constant after 30 real cold samples.
2. Budget Standard API ingestion at $0.0039 local-cold and use the external $0.0084-$0.0117 range as
   a conservative warm planning envelope until this deployment has candidate telemetry.
3. Capacity-plan by `S`, `E`, `F`, `N`, and `R`; source MB or episode count alone is insufficient.
4. Serialize ingestion within a group. Use separate clients and bounded workers across independent
   groups. Never sum all scans as elapsed time, and never divide same-group cumulative time blindly
   by the semaphore limit.
5. Keep the PR #1711 behavior. Block an upgrade if the old full-text endpoint pattern returns.
6. At about 10,000 stored edges or 250 ms edge-hybrid database p50, start weekly growth review and a
   warm retrieval suite. At 500 ms p50, open an ANN/backend/partition decision.
7. Require search p95 <=750 ms, p99 <=1.5 s, medium completion p95 <=30 s excluding queue wait, and
   no missing/duplicate/cross-group facts at the largest expected group before launch.
8. If `D` reaches 10% of API/application time earlier than planned, inspect `R/N`, invalidated-edge
   retention, concurrency, and slow plans before changing timeouts.
9. If exhaustive scans dominate before required cardinality, test a group-safe vector-index path or
   another backend. Do not assume FalkorDB Cluster splits one physical graph; it distributes separate
   graph keys.
10. Keep raw episodes in durable storage. The graph is a rebuildable derived index; current normal
    ingestion is a sequence of statements, not one episode-wide transaction.
11. Do not enable communities or bulk ingestion in the baseline until correctness, cost, recovery,
    and retrieval-quality gates pass independently.
12. Reforecast from actual cardinalities at every doubling of `R`, model or ontology change, Graphiti
    upgrade, FalkorDB upgrade, embedding-dimension change, or material change in invalidation rate.

## Sources

### Local evidence

- Measured hot-path JSON: [reports/falkordb-hotpath-20260826T233743Z-ffb8c385.json](../reports/falkordb-hotpath-20260826T233743Z-ffb8c385.json)
- Human-readable hot-path report: [reports/falkordb-hotpath-20260826T233743Z-ffb8c385.md](../reports/falkordb-hotpath-20260826T233743Z-ffb8c385.md)
- Cold API cost JSON: [reports/graphiti-cost-20260821T230704Z.json](../reports/graphiti-cost-20260821T230704Z.json)
- Cold API cost report: [reports/graphiti-cost-20260821T230704Z.md](../reports/graphiti-cost-20260821T230704Z.md)
- FalkorDB query-plan reproduction: [docs/falkordb-performance.md](falkordb-performance.md)
- Broader source analysis: [docs/graphiti-scaling.md](graphiti-scaling.md)
- Backend decision context: [docs/falkordb-vs-neo4j.md](falkordb-vs-neo4j.md)
- Benchmark implementation: [src/agent_graph_memory/falkordb_hotpath_benchmark.py](../src/agent_graph_memory/falkordb_hotpath_benchmark.py)

### Public sources

- Graphiti 0.29.3 release: https://github.com/getzep/graphiti/releases/tag/v0.29.3
- Graphiti 0.29.3 ingestion source: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/graphiti.py
- Entity extraction/resolution source: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/utils/maintenance/node_operations.py
- Fact extraction/resolution source: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/utils/maintenance/edge_operations.py
- Search implementation: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/search/search.py
- Search operations and limits: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/search/search_utils.py
- Search configuration/limit: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/search/search_config.py
- Search recipes: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/search/search_config_recipes.py
- Concurrency default: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/helpers.py
- Recent episode window source: https://github.com/getzep/graphiti/blob/v0.29.3/graphiti_core/utils/maintenance/graph_data_operations.py
- Public adding-episodes guide: https://help.getzep.com/graphiti/core-concepts/adding-episodes.md
- FalkorDB endpoint scan fix and numerical cases: https://github.com/getzep/graphiti/pull/1711
- Graphiti vector-index question: https://github.com/getzep/graphiti/issues/1055
- Public bulk latency case: https://github.com/getzep/graphiti/issues/1262
- Historical API cost case: https://github.com/getzep/graphiti/issues/467
- External fresh-versus-mature token measurement: https://github.com/aiosbrain/aios-team-brain/pull/506
- External prompt-family cost measurement: https://github.com/aiosbrain/aios-team-brain/pull/488
- Graphiti v0.27 prompt refactoring release: https://github.com/getzep/graphiti/releases/tag/v0.27.0
- Zep temporal knowledge graph paper: https://arxiv.org/abs/2501.13956
- OpenAI API prices used by the local cost report: https://developers.openai.com/api/docs/pricing
- FalkorDB vector index documentation: https://docs.falkordb.com/cypher/indexing/vector-index
- FalkorDB concurrency model: https://docs.falkordb.com/design/concurrency
