# NJ Parcel Flood Risk Dashboard — Progress Log

Newest entry on top. Never delete entries. Format per OPERATING_GUIDE.md §13.5:
Done / Decisions / ⚠ Deviations / Next (+ per-county checklists during statewide phases).

---

## 2026-08-12 — Phase 2: flood layers (NFHL + CAFE SLR 5ft), statewide (agent: sonnet-5)

**Decisions (§13.2) -- owner input received on the entry below:** given the
join-rate finding (statewide MOD-IV join rate 88.34%, below the ≥97% gate),
owner's explicit direction: **proceed with Phase 2; flag the join rate as a
known limitation** rather than investigate further or adjust the gate for now.
Recorded here per §13.3 (QA gate thresholds need owner approval to change --
this is that approval being exercised, not a unilateral change). Not resolved,
just consciously deferred with the owner's sign-off; revisit before publishing
final scores/UI copy (§5.7 disclaimer should account for it).

**Done:**
- Ported the P4 bisection pattern to P3/NFHL: `fetch_nfhl_bbox()` now uses
  `returnIdsOnly` + OBJECTID-chunking (200/chunk) + recursive bisect-on-failure
  (`_fetch_nfhl_batch`), replacing the `resultOffset` paging that was still
  failing on Cape May even after the earlier page-size reduction (2000→200).
  Verified live on Cape May alone first: all 2,712 zones recovered cleanly,
  zero bisection needed that time.
- **Found and fixed a second, different failure mode while running statewide**:
  after ~7 counties of sustained requests, `hazards.fema.gov` started forcibly
  resetting the TCP connection (`WinError 10054`) on the plain `returnIdsOnly`
  call itself -- not an ArcGIS `{"error":...}` payload, so it trips before the
  batch-level bisection logic even applies. Same class of problem already
  documented in `get_json()`'s docstring for `mapsdep.nj.gov` (an older host's
  request-budget throttling needing a longer cooldown, not faster retries).
  Fixed: raised `retries`/`backoff_base` on the `returnIdsOnly` and NFHL-batch
  calls, added a 1.5s inter-county pace in `main()`'s loop. Resumed the
  statewide run *without* `--force` afterward so the 7 already-succeeded
  counties replayed from local cache instead of re-hammering the host.
- Added `pipeline/tests/test_flood_layers.py` -- **Phase 2 had zero test
  coverage before this**. 10 offline tests (no network): `esri_rings_to_geom()`
  orientation/hole handling (untested elsewhere despite being load-bearing),
  `zone_inventory()` aggregation, and -- the most load-bearing set -- both
  `_fetch_p4_batch`/`_fetch_nfhl_batch` bisection helpers exercised via a
  monkeypatched `lib.get_json` that fails on a chosen objectId, asserting the
  good records are still recovered and the bad one is logged, not lost. Full
  suite: **23/23 passing** (13 from Phase 1 + 10 new).
- **Ran the full statewide Phase 2 ingest (21/21 counties), completed
  end-to-end for the first time**:
  - NFHL zone counts range Hudson (1,095 zones) to Bergen (12,986); every
    county produced a plausible, non-zero SFHA subset.
  - **15/21 counties have P4 (CAFE SLR 5ft) coverage** -- exact match to
    `lib.P4_COASTAL_COUNTIES`, as expected. The other 6 (Hunterdon, Morris,
    Passaic, Somerset, Sussex, Warren) correctly show "no data", not zero
    features -- the §5.2 `fut_coverage=false` distinction Phase 3 needs.
  - **13 NFHL records skipped statewide, across only 3 unique objectIds**
    (2010306, 1245792, 1345138) -- each recurs across *multiple adjacent
    counties'* results (e.g. 2010306 in Ocean, Atlantic, Gloucester, Camden,
    Burlington). Consistent with genuinely-bad source records sitting near
    multi-county bounding-box overlaps (P3 is fetched per-county bbox, not
    exact polygon, by design -- see module docstring), not a pipeline defect.
    Logged in `FLOOD_COVERAGE.md`, not silently dropped.
  - Wrote `FLOOD_COVERAGE.md` + `data/processed/flood_coverage_report.json`
    (§11 Phase 2 exit criteria: zone inventories per county + future-coverage
    map -- both produced).

**⚠ Deviations / open items:**
- The join-rate limitation from Phase 1 is carried forward, not resolved --
  see the entry below and the Decisions note above.
- Minor, pre-existing, not fixed here: §6.3 describes pipeline stages as
  "county-resumable with `--county FIPS`", but both `01_parcel_core.py` and
  `02_flood_layers.py`'s actual `--county` flags take county *names* (e.g.
  `"CAPE MAY"`), not FIPS codes -- consistent between the two scripts, just a
  documentation/wording mismatch, not a functional bug. Worth a guide wording
  fix at some point, not urgent.
- No numeric QA gate applies to Phase 2 itself -- §11's Phase 2 row only
  requires zone inventories + a future-coverage map (both done); §12.1's
  geometry-validity gates are explicitly Phase-3-scoped per the same table.
- 3 genuinely-bad NFHL source records statewide (not fixable client-side, see
  Done above) -- re-check if FEMA's NFHL data gets refreshed before Phase 3.
- Statewide `data/processed/flood_layers/` (NFHL + CAFE gpkg per county) and
  `flood_coverage_report.json` intentionally not committed (gitignored,
  matches §8's convention) -- `FLOOD_COVERAGE.md` (the human-readable summary)
  is committed.

**Next:** Phase 3 (`03_intersect.py`) -- parcel-level overlap metrics against
both the NFHL and CAFE layers (§5.2 formulas), the heaviest stage (guide's own
budget: ≤12h statewide, county-checkpointed). §12.1's geometry gates apply
here for the first time.

---

## 2026-08-12 — Phase 1 correction: PCL_MUN join-rate bug, statewide re-ingest, QA gate finding (agent: sonnet-5)

**⚠ Session note:** started as Phase 2 work. Before trusting Phase 1 as a
foundation, checked whether its exit gates (§11: join rate ≥97%, county counts
±2%) had actually been verified at statewide scale -- the 2026-08-03 entry below
explicitly flags this as *not yet done* ("Next: run `01_parcel_core.py --county
ALL`..."). Running it for real surfaced a foundational bug that invalidates that
entry's fixture-level join-rate numbers. This entry corrects the record rather
than editing the one below (this file is append-only per its own header).

**Done:**
- **Root-cause bug found and fixed:** `COUNTY`, `MUN_NAME`, `PROP_CLASS`, and the
  assessed-value fields are populated *only* when a MOD-IV tax-record join
  succeeds -- they come from the join, not the base parcel/cadastral layer.
  `01_parcel_core.py` was fetching per county via `WHERE COUNTY='X'`, which
  therefore silently returned *only already-matched* parcels -- making "join
  rate" a tautology (100% every time, since an unmatched parcel can never be
  found by a filter on a field the join itself populates). `PCL_MUN` (base
  parcel layer, populated regardless of join status) is the correct fetch key.
  Switched to `WHERE PCL_MUN LIKE '{2-digit county prefix}%'`; verified the
  prefix-to-county mapping against real records (not just assumed from the
  known convention) and added it as `COUNTY_PREFIX` in `nj_parcel_lib.py`.
- **Foundational shared-helper bug found and fixed:** ArcGIS servers report their
  own server-side errors as a `{"error": {...}}` JSON body under HTTP 200 --
  `raise_for_status()` never catches this. `get_json()` silently accepted these
  as valid (sometimes empty) responses. Now raises `RuntimeError` on that
  pattern. This was independently blocking Phase 2's P4 (CAFE) pagination too;
  fixing it once in the shared helper resolved both.
- `class_group()` crashed on missing `PROP_CLASS` (`NaN` arrives as a `float` in
  a mixed-type pandas column; `(code or "").strip()` doesn't catch it since
  `NaN` is truthy). Fixed with an explicit `isinstance(code, str)` check.
- Separated two previously-conflated QA metrics: `join_rate` (MOD-IV match
  completeness -- no code at all) vs. `unmapped_class_codes` (crosswalk
  completeness -- a real code the §5.4 table doesn't recognize). Conflating them
  had made Bound Brook's ordinary ~5% unmatched rate print as "unmapped," wrongly
  implying a failing crosswalk.
- Dedup logic per §12.1's own language ("PIN unique statewide, dupes logged +
  resolved by composite key"): exact-duplicate rows (identical in every column)
  are collapsed; genuinely-conflicting duplicate PINs are kept and counted
  (`n_dupe_pin`), never silently merged.
- `build_master()` now returns a `keep_mask` so `fetch_and_write()` filters the
  source GeoDataFrame identically before building `geoms` -- master/geoms row
  alignment guaranteed by construction, not re-derived by PIN after the fact.
- `P4_COASTAL_COUNTIES` corrected 14→15 (added Gloucester): the Phase 0 count
  was transcribed from an ArcGIS item's prose description, which was wrong --
  the live data's own `COUNTY` field shows 15 distinct counties with 2,000+
  Gloucester features, not a sliver. Fixed in `nj_parcel_lib.py` and
  `test_recon.py`; `00_recon.py --force` re-run, `RECON.md`/`recon_report.json`/
  `MANIFEST.json` regenerated.
- Rewrote `pipeline/tests/test_parcel_core.py` (13 tests, was 7): added synthetic
  offline tests (`_synthetic_gdf` helper) that directly assert the join-rate/
  crosswalk-gap separation and the exact-vs-conflicting dedup behavior, so both
  bugs above have a regression test that doesn't depend on live data. Rebuilt
  the 3-town fixture with the corrected code. Full suite: **13/13 passing.**
- **Ran the full statewide ingest** (21 counties) with all fixes applied and
  computed the QA gates for real (not just on the fixture, per §11's actual
  requirement):
  - Total parcels: **3,478,722** vs. Phase 0 recon's recorded 3,478,727 -- a
    5-record difference (0.0001%), comfortably inside the ±2% county-count gate.
  - Unmapped class codes: **0** statewide (0.0%, gate requires <0.5%) -- the
    §5.4 crosswalk itself is completely clean at full scale, confirming the
    Phase 0 8-county spot-check held up.
  - **MOD-IV join rate: 88.34% (3,073,154 / 3,478,722) -- below the required
    ≥97% gate (§11, §12.1.2). See ⚠ below.**
- Investigated Cape May County specifically (65.93%, the worst of 21 counties,
  and 486 duplicate PINs -- also far more than any other county). Checked
  whether unstable `resultOffset` pagination (no explicit `orderByFields`,
  a known ArcGIS gotcha) could be duplicating/dropping records: repeated the
  identical paginated query twice and compared -- **returned OBJECTIDs were
  identical both times, same order**, ruling this out as the cause. Sampled
  unmatched records: `QFARM` (farmland-assessment) and `C0001`/`C0003`
  (condo-unit) qualifier codes both present. Sampled duplicate PINs: a cluster
  around a "block 107.02/.07/.08/.011/.012" resubdivision series, all
  unmatched, each appearing exactly twice -- consistent with genuine
  source-data duplication (an unretired old geometry from a resurvey) rather
  than a pipeline defect, though not chased to a fully definitive root cause
  (would need an external MOD-IV source to confirm; out of scope this session).
- Phase 2 (`02_flood_layers.py`), started but not complete: NJ county-boundary
  fetch (TIGERweb) working; P4 (CAFE) fetch now fully working end-to-end
  (OBJECTID-chunk pagination + bisection fallback + the `get_json()` fix
  together -- confirmed 539/539 Cape May records recovered, where it previously
  silently returned partial/empty results). P3 (NFHL) fetch still unreliable on
  at least one county -- see ⚠ below.

**Decisions (§13.2):**
- Did **not** adjust, lower, or reinterpret the join-rate gate to make it pass.
  §13.3 lists QA gate thresholds among what must never change without owner
  approval, and §13.4 explicitly prohibits weakening gates to pass. Reporting
  the finding to the owner instead (this entry + direct chat report).
- Treated the corrected, full statewide run as the true basis for evaluating
  Phase 1's exit gates, not the fixture-only numbers recorded in the
  2026-08-03 entry below, since a fixture built with the same buggy COUNTY-fetch
  can't reveal a bug that only manifests as "the fetch itself excludes the
  failure mode."

**⚠ Deviations / open items:**
- **The 2026-08-03 entry's fixture join-rate numbers (1.0 / 1.0 / 1.0 for all
  three towns) are now known to be an artifact of the COUNTY-fetch bug, not
  real.** Not edited there (append-only log) -- correct current numbers:
  Bound Brook 95.11% (2,803 parcels, 137 unmatched), Atlantic City 99.48%
  (16,621 parcels, 87 unmatched), Mendham Boro 98.43% (1,908 parcels, 30
  unmatched, 1 exact duplicate collapsed).
- **Statewide MOD-IV join rate is 88.34%, below the required ≥97% gate.**
  Per-county range 65.93% (Cape May, worst) to 98.79% (Union, best); clear
  geographic pattern -- shore/coastal counties cluster low (Cape May 65.9%,
  Ocean 70.7%, Burlington 80.0%, Atlantic 80.2%), dense inland/urban counties
  cluster high (Union 98.8%, Morris 98.3%, Hudson 97.1%). This pattern is
  consistent with (but not proof of) a real characteristic of coastal NJ parcel
  data -- disproportionately more seasonal/vacation, condo/PUD common-element,
  and post-Sandy resubdivided parcels -- rather than a residual join-key defect,
  but this was not chased to a definitive external-source-verified root cause.
  **Needs owner input on how to proceed**: accept as a documented, real
  characteristic and revisit the gate/framing; investigate further with a
  different join strategy or an external validation source; or proceed to
  Phase 2 with this flagged as a known limitation. Full per-county table
  available in the pipeline output (not reproduced here; see
  `data/processed/parcel_master/*.parquet`, gitignored).
- Phase 2's `fetch_nfhl_bbox()` (P3/NFHL) is not yet reliable for at least Cape
  May County even after reducing page size 2000→200 -- failed again at a
  different offset (`resultOffset=800`) with the same ArcGIS
  error-under-HTTP-200 signature. `_fetch_p4_batch`'s bisection approach (which
  fixed the equivalent problem for P4) has not yet been ported to this path.
- Statewide `data/processed/parcel_master/` and `parcel_geoms/` (21 counties,
  ~3.48M parcels) intentionally not committed (gitignored, matches §8's
  data-handling convention) -- only code, tests, the 3-town fixture, and this
  log are committed.
- `ogr2ogr`/GDAL still not installed (noted since Phase 0) -- still not
  blocking either P1 or P2's current FeatureServer-query approach.

**Next:** Owner decision on the join-rate gate finding above. In parallel or
after: port bisection to `fetch_nfhl_bbox()`, get P3 working end-to-end for all
21 counties, complete Phase 2.

---

## 2026-08-03 — Phase 1: parcel core + mini-state fixture (agent: sonnet-5)

**⚠ Session note:** this phase spanned a real environment outage. Windows
Application Control started blocking pandas' compiled `dtypes.pyx` module
mid-session (`DLL load failed... An Application Control policy has blocked this
file`) -- confirmed machine-wide, not project-specific (it broke FloodOps V2's
already-working pipeline too). `01_parcel_core.py` was written and structurally
reviewed while blocked, but **never actually executed** until the block cleared on
its own (owner-side, nothing done here to force it) at the start of this entry's
session. Recorded because "the script exists" and "the script ran and passed its
own gates" are different claims, and only the second one is true here.

**Critical finding *before* writing the ingest field list (would have been a real
privacy bug otherwise):** empirically verified what `ST_ADDRESS`/`CITY_STATE`/
`ZIP_CODE` actually contain, rather than trusting the Phase 0 sample. That sample
(plain owner-occupied residential in one town) showed `ST_ADDRESS == PROP_LOC`,
which looked like "situs address, safe to keep" -- but re-tested against apartment
buildings, commercial parcels, and exempt/institutional properties and found clear
counterexamples: `ST_ADDRESS` values of `"PO BOX 43"`, `"PO BOX 5369"`, and
properties whose `ST_ADDRESS`+`CITY_STATE` point to an entirely different
municipality than `PROP_LOC`. A property cannot have a PO Box as its own street
address or be located in two towns at once -- **`ST_ADDRESS`/`CITY_STATE`/`ZIP_CODE`
are the owner's mailing address fields**, exactly what §5.6 says must never
propagate, despite being formatted like a property address. `PROP_LOC` is the real
situs-address field and is the only address field in `parcel_master`'s schema.
These fields are never requested from the source at all (not fetched-then-dropped),
consistent with §5.6's "stripped at ingest boundary."

**Done:**
- Verified the §5.4 crosswalk against the real statewide code inventory (needed
  `returnGeometry=false` on the ArcGIS distinct-values query -- without it the
  service silently returned a single bogus row instead of a real error, a genuine
  API quirk worth remembering). Sampled 8 counties spanning urban/rural/coastal:
  **0 unmapped codes** — every `PROP_CLASS` value actually in use maps cleanly.
- Wrote `01_parcel_core.py`: paginated FeatureServer ingest (2000 rows/page,
  confirmed limit), §5.4 crosswalk + unmapped-code logging, `exempt` flag derived
  from the 15A-15F set (matches the crosswalk, not a separately-maintained list),
  composite fallback key (`county_mun_block_lot_qual`) always populated per §5.1,
  geometry repair via `buffer(0)`.
- **Built and ran the mini-state fixture for real** (Bound Brook — riverine,
  explicitly required by the guide; Atlantic City — coastal; Mendham Boro, Morris
  Co. — inland, deliberately in one of the 7 counties P4 doesn't cover, so it
  exercises the `fut_coverage=false` path on purpose once Phase 2 runs). All three:
  **join_rate 1.0, 0 duplicate PINs, 0 unmapped codes, 0 invalid/empty geometries**
  post-repair. 2,666 / 16,534 / 1,879 parcels respectively.
- **Privacy field audit (§11's explicit Phase 1 exit criterion), done for real**:
  inspected the actual output schema and sample rows, not just the code -- zero
  owner-name/mailing-address columns present (`pin, county, mun_code, mun_name,
  block, lot, qual, situs_address, prop_class, class_group, exempt, land_val,
  imprvt_val, net_value, area_acres, composite_key`).
- Added `pipeline/tests/test_parcel_core.py` (7 tests: crosswalk correctness,
  unmapped/blank-code handling, exempt-flag/crosswalk consistency, fixture privacy
  audit, fixture geometry validity, master/geoms row-count and PIN-set parity).
  11/11 tests pass (4 from Phase 0 + 7 new).
- **Found and fixed a real bug by actually running the script, not just reading
  it**: `gdf[["PAMS_PIN"]]` (selecting a single non-geometry column) silently
  demotes a GeoDataFrame to a plain DataFrame; the subsequent `.geometry.is_valid`
  call resolved to a plain pandas attribute access instead of the GeoSeries
  accessor, crashing with `AttributeError`. Fixed by constructing the geoms
  GeoDataFrame explicitly from the start rather than relying on implicit type
  inference after column selection.

**Decisions (§13.2):**
- Fixture committed under `pipeline/tests/fixtures/` (small, ~7.4 MB total across
  6 files) rather than `data/processed/` (gitignored, meant for statewide-scale
  output) -- matches §8's repo layout intent ("fixtures/ (3-muni mini-state)"
  listed under `pipeline/`, distinct from the real per-county data directory).

**⚠ Deviations / open items:**
- Statewide ingest (all 21 counties, ~3.48M parcels) has **not** been run yet --
  Phase 1's exit criteria (join rate ≥97%, county counts ±2% statewide) are
  currently only verified against the 3-town fixture, not the full state. This is
  the immediate next step, not deferred to a later phase.
- `ogr2ogr`/GDAL still not installed (noted in Phase 0) -- still not blocking,
  since ingest is FeatureServer-query-based, not GDAL-based.

**Next:** run `01_parcel_core.py --county ALL` for the full statewide ingest
(21 counties), verify the QA gates for real at that scale, *then* Phase 2
(`02_flood_layers.py`).

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
