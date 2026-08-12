# NJ Parcel Flood Risk Dashboard — Flood Layer Coverage (FLOOD_COVERAGE.md)

Auto-written by `pipeline/02_flood_layers.py` (§11 Phase 2 exit criterion: zone inventories per county + a future-coverage map).

## Per-county summary

| County | FIPS | NFHL zones | NFHL SFHA zones | P4 (CAFE SLR 5ft) covered | P4 features |
|---|---|---|---|---|---|
| CAPE MAY | 009 | 0 | 0 | ✅ | 9000 |

**1/1 counties have P4 future-risk coverage.** The other 0 get `fut_coverage=false` in Phase 3/4 -- the UI must show "future data n/a here", never "no future risk" (§5.2).
