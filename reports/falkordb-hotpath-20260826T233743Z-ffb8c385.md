# FalkorDB Graphiti Hot-Path Growth Benchmark

Generated: `2026-08-26T23:37:43.631401+00:00`

This benchmark performs no OpenAI calls. Times are milliseconds; graph memory is reported by FalkorDB in MB where supported.

## Configuration

- FalkorDB: `localhost:6380`
- Plateaus: `100, 500, 1000, 2500, 5000, 10000` entities
- Warmups/samples: `2/7`
- Query timeout: `30000 ms`
- Vector dimensions/prototypes: `1536/8`

## Growth Curves

| N entities | F facts | Redis used | Graph MB | Node cosine p50/max | Edge cosine p50/max | Edge FT typical hits/p50 | Edge FT broad hits/p50 | Edge hybrid p50 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 150 | 5821624 | 1 | 1.697/2.048 | 2.197/2.670 | 8/0.544 | 150/0.648 | 2.615 |
| 500 | 750 | 13918760 | 8 | 2.443/2.610 | 7.269/7.879 | 38/0.608 | 750/1.097 | 7.900 |
| 1,000 | 1,500 | 24049048 | 16 | 3.207/3.523 | 24.073/24.707 | 75/0.632 | 1500/1.602 | 24.375 |
| 2,500 | 3,750 | 55102816 | 41 | 6.016/6.129 | 97.944/118.012 | 188/0.854 | 3750/3.171 | 117.102 |
| 5,000 | 7,500 | 105951664 | 81 | 10.757/10.868 | 158.328/190.618 | 375/0.930 | 7500/5.983 | 160.750 |
| 10,000 | 15,000 | 207823928 | 163 | 19.794/20.079 | 361.738/447.765 | 750/1.238 | 15000/11.744 | 379.699 |

## Forecasting

Each JSON curve point contains raw samples for N (entities) and F (facts). The `episode_projection` object applies measured hybrid DB p50 values to E extracted entities, episode facts, and Q searches; it excludes model and application time.

## Cleanup

- Exact benchmark graph deleted: `True`
- Absence verified with GRAPH.LIST: `True`
