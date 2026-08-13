# NJ Parcel Flood Risk Dashboard — Operating Guide

**Project:** NJ Parcel Flood Risk Dashboard — statewide parcel-scale flood exposure for financial & insurance review
**Owner:** Abdul Kalam Azad Mustaq (ar.abdulkalam.mustaq@gmail.com)
**Guide version:** 1.1 — written 2026-07-18, repo location corrected 2026-08-02
**Status:** Guide-Phase 7 (web app, §7.2) closed out — 5 views (Search & Map, Jurisdiction Summary, District Exposure, Ranked Municipalities, Methodology), global filters, CSV export, live P8 statewide address geocoding, on the locked stack (§6.2). `09_validate.py` (§12.1) run for real, statewide — **6 of 7 QA gates PASS**; the one FAIL is `join_rate=0.8834`, the already-known, owner-approved-to-carry-forward limitation (PROGRESS.md 2026-08-12). Municipality-choropleth boundary matching **564/564**. Axe/Playwright suite (§12.2): **15/15 passing**, run repeatedly and reliably (a CPU-contention flakiness issue was found and fixed by capping worker concurrency, not by loosening an assertion). The map detail-level toggle (county/muni/parcel, docked on the map) locks its own zoom floor per tier, verified via real-browser tests since this session's preview pane can't confirm animated/scroll-zoom MapLibre behavior (see the "Standing tooling caveat" below). **A full visual-design pass is done**: a real color system (custom teal `brand` scale replacing default Tailwind blue, contrast-verified and axe-confirmed), elevation (shadows/rounded corners replacing flat borders), a real type scale, the risk-band color ramp reused in stat cards/tables (not just the map), and table zebra/hover polish — driven by two rounds of `design:design-critique` against real-browser screenshots, most recently an explicit owner ask for a full overhaul, not incremental fixes. Full detail across several PROGRESS.md 2026-08-13 entries (search for "UI overhaul", "detail-level toggle", "Playwright suite"). **Known limitation, owner-approved to carry forward, not resolved:** statewide MOD-IV join rate 88.34%, below the required ≥97% gate. **Standing tooling caveat** (owner-reviewed, non-blocking): this session's preview pane intermittently fails to composite frames, stalling anything MapLibre needs `requestAnimationFrame` for (including scroll/drag-zoom) — doesn't leave any product behavior unverified; animation-dependent pieces get a real-browser Playwright check instead. Next: R2 upload (needs owner infra decision) + production deploy; portfolio assets (screenshots, `CASE_STUDY.md`).
**Guide location (canonical):** `I:\My Drive\RUTGERS\Portfolio Projects\8. NJ FLOOD RISK DASHBOARD\OPERATING_GUIDE.md`
**Source spec:** `nj_parcel_flood_risk_spec_sheet.md` (same folder) — requirements source. This guide operationalizes it; **on conflict, this guide wins** (deviations listed in §2).
**Sibling:** Project 9 (`9. NJ HAZARD DASHBOARD\`) reuses this project's **parcel core** (§6.5). Build order matters: this project first.

---

## 0. How to use this document

Written so a coding agent (Opus/Sonnet) can build the project across sessions with **no conversation history**.

1. Read this guide, then the source spec, then `PROGRESS.md` (§13.5).
2. One phase (§11) per session; all exit criteria met before advancing. Statewide phases are **county-resumable** — never restart a completed county.
3. This guide wins over the spec and your own instincts; external facts (URLs, download layouts) drift — fix per §13.2, log in PROGRESS.
4. §13.3 hard-locked; §5.6 privacy rules and §5.7 disclaimer are non-negotiable.

---

## 1. Project identity

### 1.1 What is being built

**One-liner:** A statewide New Jersey dashboard (~3.4M parcels, 21 counties, 564 municipalities) that joins MOD-IV tax-assessment attributes to parcel geometry, intersects every parcel with current (FEMA NFHL) and future (NJ climate/SLR) flood layers plus tract-level NFIP loss evidence, scores each parcel 0–100, and serves parcel search, county/municipality filtering, and district-at-risk summaries (share of residential/commercial/industrial classes at risk by count and assessed value) — with exportable tables for underwriting and portfolio review.

The spec's acceptance criteria (search by address/tax ID; county+muni filters everywhere; % of class groups at risk; count **and** assessed-value exposure; current vs future distinction; exports) are adopted verbatim as §1.4 items.

### 1.2 Why it exists (portfolio narrative)

The owner's biggest pure data-engineering artifact: statewide-scale spatial ETL (millions of features), a locked scoring model with visible drivers, and a serverless analytics UI. Extends GeoFloodFin (5 cities, 203 tracts) to all of NJ at parcel grain. Flagship for **Geospatial Intelligence**, co-billed to **Data Engineering & Applied AI**.

### 1.3 Audiences

Hiring managers (primary); insurance/flood/financial analysts and municipal planners as the credibility audience (demo only — §5.7).

### 1.4 Success criteria (measurable)

- [ ] Parcel search by address, PAMS PIN, and county+district block/lot returns a detail panel with map zoom, class, values, flood flags, score + drivers.
- [ ] County → municipality filters apply consistently to map, tables, charts, and summaries.
- [ ] District exposure view reports count **and** % at risk and assessed-value exposure per class group (§5.4), split current vs future.
- [ ] Every parcel scored 0–100 per §5.3 with drivers shown; bands render on the map at parcel zoom.
- [ ] Ranked municipality table within a county by % at risk and value at risk.
- [ ] CSV export of any filtered summary/table, with disclaimer header.
- [ ] QA gates met: MOD-IV join rate ≥ 97% statewide; county parcel counts within ±2% of source counts; geometry validity 100% post-repair.
- [ ] No owner names or owner mailing addresses anywhere in published artifacts (§5.6).
- [ ] Fully static deployment (Cloudflare Pages + R2); loads usable on mid-tier mobile.

---

## 2. Deviations from the source spec (deliberate)

| Spec says | This build does | Why |
|---|---|---|
| "Zoning district" analysis | MOD-IV property-class groups labeled "district / property-use exposure" | The spec itself prescribes this proxy; true zoning layers are a later add |
| NFIP loss indicators "where licensing permits" | OpenFEMA redacted claims aggregated to **census tract**, never parcel | Redacted dataset's spatial precision + privacy; tract evidence is defensible |
| Unspecified hosting/backend | Fully static: precomputed artifacts + PMTiles on Cloudflare R2, no server | Zero cost, zero ops, portfolio-durable; spec's own recommendation is precompute-everything |
| Real-time premium estimation etc. | Confirmed out of scope | Matches spec's own out-of-scope list |

---

## 3. Scope contract

**In scope (v1):** everything in §1.4; statewide coverage; class-group crosswalk (§5.4); current + future indicators; tract NFIP evidence; static analytics UI.
**Out of scope (hard):** premium estimation, claims workflows, building-level engineering models, accounts/auth (all per spec); any parcel-level claims display; owner identity display; live data feeds; write APIs.
**Stretch (after Phase 8):** DuckDB-WASM in-browser parcel explorer (§7.4); municipal zoning overlays for 2–3 towns; time-series MOD-IV (multi-year) trends.

---

## 4. Data sources

| # | Dataset | Primary source | Access | Fallback |
|---|---|---|---|---|
| P1 | Statewide parcel geometry + MOD-IV attributes | NJGIN/NJOGIS **"Parcels and MOD-IV Composite of NJ"** (FGDB/GPKG download; large) | download + GDAL | per-county parcel downloads; raw MOD-IV extracts (NJ Treasury) joined by PAMS PIN |
| P2 | Raw MOD-IV tax list (enrichment/validation) | NJ Treasury / NJGIN MOD-IV products | download | skip (composite-only) |
| P3 | Current flood hazard | FEMA **NFHL** for NJ (SFHA zones A/AE/AO/AH/VE; shaded X = 0.2%) | state GDB download or ArcGIS REST | MSC downloads by county |
| P4 | Future flood indicators | NJDEP climate-adjusted / sea-level-rise inundation layers (NJDEP Bureau of GIS; Rutgers NJ ADAPT / NJ FloodMapper layers) — **verify exact layers in Phase 0** | ArcGIS REST / download | use NJDEP Inland Flood Protection–related layers; if none usable, future flag = SLR-only with documented coverage |
| P5 | Flood design/profile context | NJGIN flood design-flood / flood profile layers | download | omit (context only) |
| P6 | NFIP loss evidence | OpenFEMA **FIMA NFIP Redacted Claims** (CSV/API) → aggregate to census tract | download | omit component, reweight per §5.3 note |
| P7 | Boundaries | TIGER counties/munis (or NJOGIS munis), TIGER tracts | download | — |
| P8 | Geocoding for address search | NJGIN/NJOGIS composite geocoder REST — verify | client-side REST | US Census Geocoder |
| P9 | Basemap | OpenFreeMap vector tiles | MapLibre style | Carto raster |

**Handling rules:** raw data gitignored; `data/MANIFEST.json` entries (`name, source_url, retrieved_utc, sha256, license_note`); disk budget — expect **~40–60 GB** working space locally (document actual in PROGRESS); all heavy outputs county-partitioned (`{fips}` = 21 counties); published artifacts budgeted per §7. Working CRS EPSG:26918 (meters); published CRS EPSG:4326.

---

## 5. Methodology (LOCKED — changes require owner approval)

### 5.1 Parcel master

One row per parcel keyed by **PAMS PIN** (fallback composite key `county+muni_code+block+lot+qual`). Fields: identifiers (PIN, county, muni code/name, block, lot, qual), situs address, property class code, class group (§5.4), land/improvement/total assessed value, exempt flag, area, centroid, geometry ref. **Strip at ingest boundary and never propagate:** owner name, owner mailing address, and any care-of fields (§5.6).

### 5.2 Flood indicators (per parcel)

- `cur_risk`: overlap with SFHA (`sfha_pct` = % parcel area in A*/V* zones) and `mod_risk_pct` (shaded X). Current flag = `sfha_pct > 0`; moderate flag = `mod_risk_pct > 0`.
- `fut_risk`: overlap % with the Phase-0-verified future layer set (union), with per-layer sub-fields. Future flag = overlap > 0. If future coverage is partial (e.g., coastal-only SLR), inland parcels get `fut_coverage = false` and the UI must show "future data n/a here", never "no future risk".
- Overlap computed on geometry intersection area ÷ parcel area; slivers < 1% of parcel area or < 10 m² dropped.
- `tract_loss`: parcel's tract NFIP claims per 1,000 parcels (P6), as statewide percentile.

### 5.3 Composite score (0–100) and bands

Component values in [0,1]:
- `C_cur = max(sfha_pct_frac, 0.3·has_sfha) + 0.15·(mod_risk_pct_frac)` capped at 1 — presence floor 0.3 so a touched parcel never scores trivially low.
- `C_fut = max(fut_pct_frac, 0.3·has_fut)` capped at 1; if `fut_coverage = false`, `C_fut = C_cur × 0.5` and driver panel says "future estimated from current (no future data here)".
- `C_loss = tract claims-density percentile` (0–1); if P6 unavailable, redistribute its weight proportionally to the other two and record the variant in `meta.json`.

**`score = round(100 × (0.45·C_cur + 0.30·C_fut + 0.25·C_loss))`**
Bands: 0 = none; 1–24 low; 25–49 moderate; 50–74 high; 75–100 severe. The parcel panel must show all three component values and the inputs behind them (the "drivers" requirement).

### 5.4 Class-group crosswalk (MOD-IV property class → reporting groups; LOCKED)

| Group | MOD-IV classes |
|---|---|
| Residential | 2 (residential), 4C (apartments) |
| Commercial | 4A |
| Industrial | 4B |
| Farm/Agricultural | 3A, 3B |
| Vacant | 1 |
| Public/Institutional/Exempt | 15A–15F |
| Other (rail/utility/misc) | 5A, 5B, 6A, 6B, and any unmapped code (logged) |

Verify code inventory against the actual MOD-IV extract in Phase 1; unmapped codes go to Other with a logged count, never silently dropped.

### 5.5 Aggregates (exact formulas from the spec)

Per geography (county, muni) × class group × risk lens (current | future | either): parcel count, at-risk count, **% at risk = at-risk/total × 100**, total assessed value, value at risk (presence-based = full value of at-risk parcels — headline; overlap-based = value × overlap fraction — companion), **value exposure % = at-risk value/total value × 100**. Plus geography-level rollups and the ranked-municipality table.

### 5.6 Privacy rules (NON-NEGOTIABLE)

No owner names, owner mailing addresses, or care-of lines in any processed artifact, tile, export, or UI surface — stripped at ingest (§5.1). NFIP claims never shown below tract level. If a source field is ambiguous (could identify a person), exclude it and log.

### 5.7 Standing disclaimer (verbatim; restyle only) — every page footer + export header

> **Screening tool — not a flood determination.** This dashboard is a portfolio project combining public parcel, FEMA, NJDEP, and OpenFEMA data with simplified assumptions. Scores are relative screening indicators, not insurance ratings, legal flood-zone determinations, or property valuations. Verify any parcel with official FEMA maps (msc.fema.gov), NJDEP, and municipal records.

---

## 6. Architecture

### 6.1 Shape

```
Python ETL (local, county-partitioned)                Static app (Cloudflare Pages)
P1..P7 → parcel core → intersections → scores  ──▶   MapLibre + PMTiles (R2)
→ aggregates (DuckDB) → artifacts:                    summaries JSON + search shards
   tiles (tippecanoe) · parquet · JSON                 client geocode (P8) only
```

No backend. The only runtime network calls: basemap, R2 artifacts, and the P8 geocoder.

### 6.2 Stack (LOCKED)

Python 3.11+ (`uv`): `duckdb` (+spatial), `geopandas`/`pyogrio`, `shapely>=2`, `pyarrow`, `requests`, `pytest`, `ruff`; GDAL/`ogr2ogr` for FGDB ingest. **Tiles:** tippecanoe via Docker or WSL (not native Windows — document the chosen route in PROGRESS). Web: Vite + React 18 + TS strict + Tailwind v4 + MapLibre GL + `pmtiles` protocol. Hosting: Cloudflare Pages (app) + **R2 free tier** (tiles + parquet; public bucket, CORS enabled). No scheduled jobs — refresh is a manual annual/quarterly rerun (§6.4).

### 6.3 Pipeline stages (`pipeline/`, all county-resumable with `--county FIPS`, idempotent)

`00_recon.py` (verify P1–P9, record sizes/layouts) · `01_parcel_core.py` (ingest composite → privacy strip → class groups → `parcel_master/{fips}.parquet`) · `02_flood_layers.py` (NFHL + future layers, normalized) · `03_intersect.py` (overlap metrics per §5.2; the heavy stage — budget ≤ 12 h statewide, checkpoint per county) · `04_claims.py` (P6 → tract percentiles) · `05_score.py` (§5.3) · `06_aggregate.py` (§5.5 into DuckDB → JSON artifacts) · `07_tiles.py` (GeoJSONL → tippecanoe → PMTiles) · `08_search_index.py` (per-muni shards) · `09_validate.py` (QA gates §12.1).

### 6.4 Update frequency

Parcels/MOD-IV: annual (or when NJGIN updates); NFHL: quarterly check; future layers: on NJDEP release; claims: annual. Each rerun bumps `meta.json` vintages; the UI shows them.

### 6.5 Parcel core contract (consumed by Project 9)

`parcel_master/{fips}.parquet` (schema §5.1 minus geometry) + `parcel_geoms/{fips}.gpkg` + the §5.4 crosswalk + search shards are a **public contract**: Project 9 copies these artifacts (with MANIFEST provenance) instead of rebuilding. Don't rename fields casually — that breaks the sibling.

---

## 7. Published artifacts & app

### 7.1 Artifacts (R2 unless noted)

- `tiles/parcels.pmtiles` — z13–16, minimal attrs (PIN, band, class group, flags); target ≤ 4 GB.
- `tiles/boundaries.pmtiles` — counties/munis with summary attrs for choropleths at z<13; small, may live in Pages.
- `summaries/state.json`, `summaries/county/{fips}.json`, `summaries/muni/{fips}{mun}.json` (≤ 300 KB each; Pages).
- `search/{fips}/{mun}.json.gz` — address/block-lot/PIN → PIN + centroid (lazy-loaded per selected muni).
- `parcels/{fips}/{mun}.parquet` — full scored rows for table drill-down + stretch WASM explorer.

### 7.2 App views (per spec §Interface)

1. **Search & map** — search bar (address via P8 geocode → point → parcel hit; or PIN/block-lot via shard), county→muni filters, map (choropleth < z13, parcels ≥ z13 colored by band), parcel detail panel (attrs, flags, score + drivers §5.3).
2. **Jurisdiction summary** — KPI cards (total, at-risk, % at risk, value at risk) for active geography.
3. **District exposure** — bar chart % at risk by class group; stacked current-vs-future; count and value toggles; table.
4. **Ranked municipalities** — within selected county, by % at risk and value at risk.
Filters (global, consistent everywhere): county, muni, class group, band, current|future lens, min overlap %, min assessed value. Exports: CSV of any visible table with disclaimer header + vintages. Standards: WCAG 2.2 AA; bands colorblind-safe (sequential, not red-green only) + always labeled; mobile-usable; map interactions degrade gracefully without WASM.

---

## 8. Repository

**Location (LOCKED, corrected 2026-08-02):** `C:\Users\abdul\Documents\GitHub\nj-parcel-flood`; public GitHub `nj-parcel-flood`. (Guide v1.0 originally specified `C:\Users\abdul\projects\nj-parcel-flood` — that convention was superseded once real GitHub repos were set up for the FloodOps projects; `Documents\GitHub\` is now the standing convention for all portfolio code repos.) Drive folder = spec + guide + case-study assets only.

```
nj-parcel-flood/
├── OPERATING_GUIDE.md  PROGRESS.md  RECON.md  README.md
├── pipeline/            # stages 00–09 + tests/ + fixtures/ (3-muni mini-state)
├── data/                # raw/ (gitignored), processed/ (county parquet/gpkg, gitignored), MANIFEST.json
├── artifacts/           # small committed JSON (summaries, meta); big ones → R2 (upload script)
├── web/                 # Vite app
└── .github/workflows/   # ci.yml (tests on fixtures only — never statewide data in CI)
```

---

## 11. Phased build plan

| Phase | Work | Exit criteria (gates) |
|---|---|---|
| **0. Bootstrap + recon** | Repo, env, CI; `00_recon` verifies P1–P9 incl. future-layer identification (P4) and geocoder (P8); disk plan | RECON documents every source + chosen future-layer set + sizes |
| **1. Parcel core** | `01` statewide; crosswalk; **mini-state fixture** built (3 munis: one coastal, one riverine — include Bound Brook — one inland) | Join rate ≥ 97%; county counts ±2%; privacy strip verified by field audit; fixture committed |
| **2. Flood layers** | `02` NFHL + future set normalized | Zone inventories per county logged; future coverage map produced |
| **3. Intersections** | `03` statewide (county-checkpointed) | All counties complete; sliver rule applied; §12.1 geometry gates pass |
| **4. Claims + scores** | `04`, `05` | Score distribution sanity (§12.1.5); drivers stored |
| **5. Aggregates** | `06` all geographies × groups × lenses | Rollup invariant: muni sums = county = state (±0.1%); spec formulas reproduced on fixture by hand-check |
| **6. Tiles + artifacts** | `07`, `08`; R2 upload + CORS | Budgets met; tiles render statewide; search shards resolve 20 test lookups |
| **7. Web app** | §7.2 views + filters + exports | §1.4 search/filter/summary/export boxes check on preview |
| **8. QA + launch** | `09` full gates, known-area validation, README, portfolio assets | All §1.4 checked; production URL live |

---

## 12. Testing & verification

### 12.1 QA gates (`09_validate.py` + pytest on fixture)

1. Uniqueness: PIN unique statewide (dupes logged + resolved by composite key).
2. Completeness: join rate ≥ 97%; unmapped class codes < 0.5% of parcels.
3. Geometry: 100% valid post-repair; no empty geoms; area > 0.
4. Consistency: overlap fractions ∈ [0,1]; flags ⇔ overlaps; score reproducible from stored components (recompute check).
5. Distribution sanity: statewide % parcels with `cur` flag within a plausible envelope (recon records NFHL SFHA share; alert if parcel-flag share deviates wildly); Bound Brook, Manville, coastal Atlantic/Ocean County munis rank high in % at risk — if not, stop and investigate before publishing.
6. Rollup invariants (Phase 5 gate).
7. Privacy audit: grep processed artifacts + tiles attributes for owner-name fields — must be absent.

### 12.2 Web checks

Lint/typecheck/build; Playwright: search by PIN → panel; county→muni filter cascades; district chart matches summary JSON; export downloads with disclaimer. Axe: zero serious violations.

### 12.3 Manual per-release

QGIS spot-check 10 parcels (5 known floodplain, 5 upland) against NFHL; verify 3 munis' summary numbers by independent DuckDB query; phone check.

---

## 13. Instructions for coding agents

### 13.1 Session protocol

Guide → spec → PROGRESS → env check → one phase (county-resumable stages: continue, never restart) → gates → PROGRESS entry → commit, push.

### 13.2 Decision rules (apply without asking)

Source moved → fallback (§4) → else current official source, recorded. Composite lacks a needed MOD-IV field → join P2 by PIN. A county's download is corrupt → refetch once, then log and continue with remaining counties (gate blocks Phase completion until resolved). Geometry errors → `make_valid`, log counts. Tile size over budget → drop attrs / raise minzoom before simplifying geometry. Ambiguous class code → Other + log. Anything visual → owner's portfolio design language.

### 13.3 Never change without owner approval

Score formula, weights, floors, bands (§5.3); crosswalk (§5.4); aggregate formulas (§5.5); privacy rules (§5.6); disclaimer (§5.7); parcel-core contract fields (§6.5); stack; repo location; QA gate thresholds.

### 13.4 Prohibited at all times

Publishing owner identities or sub-tract claims data; fabricating or hand-editing values/scores; committing raw statewide data or secrets; presenting output as flood determinations or insurance advice; weakening QA gates to pass; force-pushing `main`.

### 13.5 PROGRESS.md format

Dated entries, newest first: **Done / Decisions / ⚠ Deviations / Next** (+ per-county checklists during statewide phases). Never delete entries.

---

## 14. Portfolio integration

Flagship for **Geospatial Intelligence** (`/geospatial/`), cross-listed in **Data Engineering & Applied AI**. Phase 8: save to `8. NJ FLOOD RISK DASHBOARD\case-study-assets\`: screenshots (statewide choropleth, parcel panel with drivers, district exposure chart, ranked munis), pipeline-scale stats (parcels processed, runtimes), and draft `CASE_STUDY.md`. Production URL gets a `/qr/` code. Narrative hook: "GeoFloodFin at statewide scale, productized."

---

## 15. Glossary

**MOD-IV** — NJ's statewide property tax assessment system; source of class codes and assessed values. **PAMS PIN** — statewide parcel identifier linking geometry to MOD-IV. **Block/lot/qual** — municipal tax identifiers. **NFHL / SFHA** — FEMA National Flood Hazard Layer / Special Flood Hazard Area (1% annual chance); shaded X = 0.2%. **NJGIN/NJOGIS** — NJ's geospatial data infrastructure/office. **OpenFEMA redacted claims** — public NFIP claims records with privacy masking. **PMTiles** — single-file tile archive served by HTTP range requests (no tile server). **Presence floor** — minimum component credit for any nonzero overlap (§5.3). **Ratable base** — a municipality's total assessed value.

---

*End of guide. When in doubt: §13.2. When it's slow: partition by county, don't cut corners.*
