# NJ Parcel Flood Risk Dashboard — Flood Layer Coverage (FLOOD_COVERAGE.md)

Auto-written by `pipeline/02_flood_layers.py` (§11 Phase 2 exit criterion: zone inventories per county + a future-coverage map).

## Per-county summary

| County | FIPS | NFHL zones | NFHL SFHA zones | P4 (CAFE SLR 5ft) covered | P4 features |
|---|---|---|---|---|---|
| ATLANTIC | 001 | 3840 | 925 | ✅ | 7491 |
| BERGEN | 003 | 12986 | 5322 | ✅ | 1863 |
| BURLINGTON | 005 | 11317 | 3986 | ✅ | 6211 |
| CAMDEN | 007 | 6423 | 2593 | ✅ | 1626 |
| CAPE MAY | 009 | 2712 | 663 | ✅ | 9539 |
| CUMBERLAND | 011 | 3112 | 987 | ✅ | 5792 |
| ESSEX | 013 | 3793 | 1594 | ✅ | 334 |
| GLOUCESTER | 015 | 5688 | 2067 | ✅ | 2543 |
| HUDSON | 017 | 1095 | 136 | ✅ | 1157 |
| HUNTERDON | 019 | 2864 | 1579 | ❌ no data | — |
| MERCER | 021 | 5324 | 2619 | ✅ | 577 |
| MIDDLESEX | 023 | 9106 | 4431 | ✅ | 2858 |
| MONMOUTH | 025 | 12020 | 5965 | ✅ | 3893 |
| MORRIS | 027 | 5412 | 2553 | ❌ no data | — |
| OCEAN | 029 | 2926 | 1218 | ✅ | 5309 |
| PASSAIC | 031 | 10299 | 3781 | ❌ no data | — |
| SALEM | 033 | 3927 | 1478 | ✅ | 4259 |
| SOMERSET | 035 | 5391 | 2786 | ❌ no data | — |
| SUSSEX | 037 | 2587 | 1287 | ❌ no data | — |
| UNION | 039 | 1777 | 803 | ✅ | 1119 |
| WARREN | 041 | 2562 | 1500 | ❌ no data | — |

**15/21 counties have P4 future-risk coverage.** The other 6 get `fut_coverage=false` in Phase 3/4 -- the UI must show "future data n/a here", never "no future risk" (§5.2).

**13 NFHL record(s) skipped statewide** (same server-side query error pattern as P4, reproduced directly against the source -- not a client-side/rate-limit issue). Logged here, not silently dropped:

- OCEAN: objectIds [2010306]
- ATLANTIC: objectIds [2010306]
- GLOUCESTER: objectIds [2010306]
- CAMDEN: objectIds [2010306]
- PASSAIC: objectIds [1345138]
- HUNTERDON: objectIds [1245792]
- SUSSEX: objectIds [1245792, 1345138]
- WARREN: objectIds [1245792, 1345138]
- MORRIS: objectIds [1245792, 1345138]
- BURLINGTON: objectIds [2010306]
