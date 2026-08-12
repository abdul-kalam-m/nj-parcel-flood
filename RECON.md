# NJ Parcel Flood Risk Dashboard — Data Source Recon (RECON.md)

Generated: 2026-08-12T05:11:40.183021+00:00 · auto-written by `pipeline/00_recon.py` (§4).

## Data sources (P1-P9)

| # | Source | Status | Detail |
|---|---|---|---|
| | P1 parcels (NJOGIS Parcels_Composite_NJ_WM) | ✅ | Bulk .gdb.zip on geoapps.nj.gov is Incapsula-blocked to plain requests; use this FeatureServer for query-based county-by-county ingest instead. |
| | P3 FEMA NFHL | ✅ | Guide's original hazards.fema.gov/gis/nfhl/rest/... path 404s (WebSEAL error) -- corrected to /arcgis/rest/... 2026-08-02. |
| | P4 NJDEP Tidal CAFE SLR 5ft | ✅ | Single scenario (+5 ft over FEMA coastal SFHA), not multiple SLR increments. Coastal-only -- inland counties get fut_coverage=false per §5.2, exactly as the guide's partial-coverage contingency anticipated. An ArcGIS *item* pointing at this URL is flagged 'deprecated' but the live MapServer layer is what NJDEP's own current DCAT catalog names -- treated as a stale item label. |
| | P6 OpenFEMA NFIP Redacted Claims | ⚠️ unavailable | CONFIRMED UNAVAILABLE 2026-08-02: metadata endpoint works (dataset exists, lastRefresh 2025-12-19) but the live query endpoint returns HTTP 503. Consistent with public reporting of a suspension of FimaNfipClaims/FimaNfipPolicies access. Bulk CSV/parquet export URLs from the metadata also 403 (Akamai) to a plain request. §5.3's documented fallback applies: redistribute C_loss's 0.25 weight proportionally to C_cur/C_fut (effective ~0.643/0.357), record the variant in meta.json. Re-check before Phase 4, not assumed fixed. |
| | P7 TIGERweb State_County | ✅ | Same service family already proven working in the FloodOps projects. |
| | P8 NJ statewide geocoder | ✅ | The Addr_NJ_cascade service name some pages advertise 404s -- NJ_Geocode is the real, live one, confirmed 2026-08-02. |
| | P9 OpenFreeMap basemap | ✅ |  |

P2 (raw MOD-IV enrichment) and P5 (flood design/profile context) are lower-priority per the guide (fallback/context-only) and were not deep-verified in this pass -- defer to Phase 1/2 when actually needed.

## Local tooling

- `ogr2ogr` on PATH: **NO — install via conda-forge or OSGeo4W before Phase 1**
- tippecanoe route: **docker** (docker working: True, wsl on PATH: True)
