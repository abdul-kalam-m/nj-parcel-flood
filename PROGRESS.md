# NJ Parcel Flood Risk Dashboard — Progress Log

Newest entry on top. Never delete entries. Format per OPERATING_GUIDE.md §13.5:
Done / Decisions / ⚠ Deviations / Next (+ per-county checklists during statewide phases).

---

## 2026-08-02 — Phase 0: bootstrap + recon (agent: sonnet-5)

**Done:**
- Bootstrapped repo at `C:\Users\abdul\Documents\GitHub\nj-parcel-flood` (git `main`),
  dir tree per §8, `pipeline/pyproject.toml` (duckdb+spatial, geopandas, pyogrio,
  shapely, pyarrow, requests), CI skeleton, README, this file. Corrected the guide's
  original repo-location path (`Users\abdul\projects\...`, superseded once real
  GitHub repos were set up for the FloodOps projects) in both the repo copy and the
  canonical portfolio copy of `OPERATING_GUIDE.md`.
- Environment check before committing to anything: **515 GB free disk** (comfortably
  covers the guide's ~40–60 GB estimate), **Docker available** (29.6.1) — resolves
  the tippecanoe route question, WSL2/Ubuntu also available as backup.
  **`ogr2ogr`/GDAL is NOT on PATH** — needs installing (conda-forge or OSGeo4W)
  before Phase 1, though the actual P1 ingest plan below doesn't strictly need it
  (uses the FeatureServer, not the bulk GDB).
- Wrote `pipeline/nj_parcel_lib.py` + `pipeline/00_recon.py`, ran it live, wrote
  `RECON.md` + `data/processed/recon_report.json` + `data/MANIFEST.json` entries.
  4/4 offline pytest pass.

**P1–P9 verified live (not trusted from the guide's 2026-07-18 draft, which had one
confirmed-stale URL and one dataset that turned out to be genuinely unavailable):**
- **P1 (parcels):** the bulk `.gdb.zip` on `geoapps.nj.gov` is behind Incapsula bot
  protection — a plain `requests` call gets a 403. Found the actual mechanism instead:
  NJOGIS's own authoritative hosted FeatureServer
  (`services2.arcgis.com/.../Parcels_Composite_NJ_WM/FeatureServer/0`,
  `contentStatus: public_authoritative`, not one of several unofficial re-hosted
  copies that also show up in search). **Real record count: 3,478,727** — matches
  the guide's "~3.4M" estimate almost exactly. `maxRecordCount: 2000` (pagination
  constraint for Phase 1). **Verified the `OWNER_NAME` privacy claim empirically,
  not just trusted the description**: 0/510 non-blank across two different counties
  (Essex, Ocean) — Daniel's Law redaction really is applied at the source, though
  Phase 1 must still strip defensively per §5.6 rather than rely on it alone.
- **P3 (FEMA NFHL):** the guide's assumed URL
  (`hazards.fema.gov/gis/nfhl/rest/services/...`) 404s (WebSEAL error page — a stale
  path). Corrected to `hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer`;
  confirmed layer 28 = "Flood Hazard Zones", the one that matters for §5.2.
- **P4 (future layers) — the item the guide explicitly flagged "verify in Phase 0":**
  identified as NJDEP's **Tidal Climate Adjusted Flood Elevation (CAFE SLR 5ft)**,
  live, 54,571 features. **Single scenario** (+5 ft added to the FEMA coastal SFHA),
  not a set of SLR increments — §4/§5.2 language anticipated a "layer set" but there's
  really just the one usable layer. NAVD88 (ftUS) height reference. **Coastal-only:
  14 of NJ's 21 counties** (Atlantic, Bergen, Burlington, Camden, Cape May,
  Cumberland, Essex, Hudson, Mercer, Middlesex, Monmouth, Ocean, Salem, Union) —
  the other 7 (Gloucester, Hunterdon, Morris, Passaic, Somerset, Sussex, Warren) will
  need `fut_coverage=false` in Phase 2, exactly the partial-coverage scenario §5.2
  already designed for, not a surprise requiring a design change. Note: an ArcGIS
  *item* pointing at this same URL is labeled "deprecated" in its own metadata, but
  the live service and NJDEP's current DCAT catalog both say otherwise — treated as
  a stale item-level label, not a real service problem (re-verify if Phase 2 sees
  different behavior).
- **P6 (NFIP claims) — confirmed genuinely unavailable, not just a wrong URL:** the
  dataset-metadata endpoint works (confirms the dataset exists, `lastRefresh
  2025-12-19`), but the live query endpoint returns **HTTP 503** ("FEMA.gov is
  experiencing technical difficulties"), and the bulk CSV/parquet export URLs the
  metadata itself points to return 403 (Akamai bot protection). Independently
  consistent with public reporting that FEMA suspended FimaNfipClaims/
  FimaNfipPolicies access. **This isn't treated as a blocker** — §5.3 already has a
  documented fallback for exactly this (`C_loss` unavailable → redistribute its 0.25
  weight proportionally to `C_cur`/`C_fut`, giving effective weights ≈0.643/0.357;
  record the variant in `meta.json`). Re-check before Phase 4 rather than assume
  it's fixed by then.
- **P7 (TIGER):** same service family already proven in the FloodOps projects, no
  surprises.
- **P8 (geocoder):** the `Addr_NJ_cascade` service name some pages advertise 404s;
  the real, live one is `geo.nj.gov/arcgis/rest/services/Tasks/NJ_Geocode/GeocodeServer`.
- **P9 (basemap):** OpenFreeMap, live, no issues.
- **P2 / P5:** lower-priority per the guide (enrichment/context-only) — not
  deep-verified this pass, deferred to whenever Phase 1/2 actually needs them.

**Decisions (§13.2):**
- P1 ingest will be FeatureServer-query-based (paginated, 2000 records/page,
  county-partitioned via `WHERE COUNTY=...`), not GDAL-based bulk-GDB ingest — this
  sidesteps both the Incapsula block and the missing-`ogr2ogr` gap. If a future
  session wants the bulk-GDB route instead (e.g., for speed), install GDAL first and
  re-evaluate; don't assume the Incapsula block will simply go away.
- P4's "future layer set" is one layer, not several — §5.2's `fut_risk` "union of
  the Phase-0-verified future layer set" language should be read as a union over a
  set of size one for this project, not evidence something is missing.
- CI's recon-smoke step needs real dependencies installed first (`uv sync --extra
  dev` before `uv run python 00_recon.py --check-only`) — the original skeleton
  assumed a stdlib-only recon script (copying FloodOps V2's convention) without
  checking that *this* recon script's actual job (probing 7 live external services)
  genuinely requires `requests`. Fixed before it could fail in CI.

**⚠ Deviations / open items:**
- Real, measured disk usage still pending — Phase 0 didn't download any bulk data
  (recon only probes liveness/schema), so the guide's ~40–60 GB estimate is carried
  forward as a placeholder, not yet replaced with a measured number. Qualitative
  read after seeing real record counts (3.48M parcels via paginated queries, 54.6K
  P4 features, TIGER boundaries small): the guide's estimate looks conservative
  relative to 515 GB free, not a real risk, but Phase 1 should log the actual
  figure once real ingest happens rather than assume this holds.
- `ogr2ogr`/GDAL not installed — not currently blocking (P1's plan doesn't need it),
  but install before Phase 1 in case any P2/P5/fallback path ends up needing it.
- P6 unavailability needs a human decision eventually: is a ~7-month-old
  `lastRefresh` (2025-12-19) still worth treating as "current" data once/if the API
  comes back, or should Phase 4 proceed with the §5.3 fallback permanently? Not
  decided here — flagging for whoever runs Phase 4.

**Next:** Phase 1 — `01_parcel_core.py` (statewide FeatureServer ingest, privacy
strip, §5.4 crosswalk, mini-state fixture: one coastal + one riverine incl. Bound
Brook + one inland municipality).

---
