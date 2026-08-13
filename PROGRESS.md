# NJ Parcel Flood Risk Dashboard — Progress Log

Newest entry on top. Never delete entries. Format per OPERATING_GUIDE.md §13.5:
Done / Decisions / ⚠ Deviations / Next (+ per-county checklists during statewide phases).

---

## 2026-08-13 — Guide-Phase 7 (§7.2): web app (agent: sonnet-5)

The app itself: Vite + React 18 + TS strict + Tailwind v4 + MapLibre GL +
`pmtiles` protocol, exactly the locked stack (§6.2). All 4 views, global
filters, CSV export. One major, retroactive bug found and fixed along the
way (below) that also corrects Phase 6's own record.

**Done:**
- Scaffolded `web/` (`npm create vite -- --template react-ts`), Tailwind v4
  via `@tailwindcss/vite`, MapLibre GL + `pmtiles`, `react-router-dom` for
  the 4 views. Dev-mode data loading: a small Vite plugin
  (`serveArtifacts`) serves the repo's `artifacts/` directory at `/data/*`
  with proper HTTP Range support (PMTiles reads byte ranges out of a
  multi-hundred-MB archive, not the whole file -- this isn't optional).
  Production build reads `VITE_DATA_BASE_URL` (the eventual R2 URL)
  instead; the view code is source-agnostic either way.
- Added `artifacts/geography_index.json` (21 counties, 564 munis, names +
  codes) for the county/muni filter dropdowns -- generated from
  `pipeline/07_tiles.py`'s own already-tested `build_mun_lookup()` rather
  than hand-transcribing NJ's municipality names a second time. Added
  `artifacts/meta.json` (per-source retrieval dates from `data/MANIFEST.
  json`) so CSV exports carry real vintages (§7.2/§6.4), not a broken
  pointer to a file the web app was never going to be able to fetch.
- **Search & Map**: county→muni filters, address/PIN/block-lot search
  scoped to the selected muni (§7.1's own "lazy-loaded per selected muni"
  design, followed as specified -- live P8 geocoding is a separate,
  not-yet-wired path, noted below), MapLibre map with a choropleth below
  z13 and individual parcels at z13+, parcel detail panel. Re-tiled
  `parcels.pmtiles` mid-build with a richer attribute set (score, C_cur/
  C_fut/C_loss, sfha_pct/mod_risk_pct/fut_pct, address, block/lot/qual,
  assessed value, county/muni) once it became clear the original minimal
  attrs (pin/band/class_group/flags) couldn't support a real detail panel
  without a second parquet fetch per click -- and §7.2 wants the base map
  to work without depending on a WASM parquet reader (DuckDB-WASM is the
  explicit §7.4 *stretch* explorer, not the base experience).
- **Jurisdiction Summary**, **District Exposure**, **Ranked
  Municipalities**: built against the real summary JSON schemas (verified
  from actual files under `artifacts/summaries/`, not guessed from prose).
  District Exposure's "stacked current-vs-future" is rendered as grouped
  (side-by-side) bars, not literally stacked/summed -- a parcel can be
  both current- and future-at-risk, so summing would double-count; noted
  in the UI copy itself, not just here.
- Global filters (county, muni, class group, band, lens, min overlap %,
  min assessed value) wired into all 4 views and into the MapLibre layer
  filter expression for the parcel layer.
- CSV export with disclaimer header (§5.7, verbatim) + real per-source
  vintages (from `meta.json`) on all 3 table views.
- WCAG 2.2 AA pass (not a full automated audit -- see Deviations):
  colorblind-safe band ramp (ColorBrewer YlOrRd, deliberately not
  red-green), **contrast ratios computed, not eyeballed** -- the first-pass
  band text colors failed at the sizes actually used (`moderate` 4.04:1,
  `high` 3.92:1, both under the 4.5:1 normal-text threshold; only
  qualified at the looser 3:1 large-text/UI bound), fixed with black text
  on both, verified 9.05:1 and 5.35:1. Skip-to-content link, visible focus
  rings, semantic landmarks/headings, labeled form controls throughout.
  Checked "mobile-usable" structurally (375px viewport, zero horizontal
  overflow) since the live visual screenshot tool wasn't cooperating at
  that point in the session (see Deviations).
- `npm run build` (`tsc -b && vite build`) actually run, not assumed --
  caught two real type errors `tsc --noEmit` alone had missed (project-
  build mode is stricter): a MapLibre layer-click handler typed as the
  base `MapMouseEvent` instead of `MapLayerMouseEvent` (the one that
  actually carries `.features`), and a class-group union comparison
  TypeScript flagged as vacuous. Both fixed properly, not suppressed;
  clean production build confirmed after.

**The major finding -- tippecanoe was never actually writing PMTiles:**
Building the map surfaced that `klokantech/tippecanoe`'s binary has no real
PMTiles output support at all -- `tippecanoe --help` only documents
`--output=x.mbtiles`. Handing it a `.pmtiles` filename doesn't error, it
silently writes MBTiles (SQLite) content to that path regardless of the
extension. Confirmed directly: the file's own first bytes read `SQLite
format 3`, not PMTiles' `PMTi` magic, for *both* tilesets guide-Phase 6
had reported as complete. File-size and row-count checks (what guide-Phase
6 actually verified) can't catch a wrong internal format -- this was only
caught now because the web app finally tried to *read* one with a real
PMTiles client. Fixed in `pipeline/07_tiles.py`: tippecanoe now outputs
real `.mbtiles`, then `protomaps/go-pmtiles convert` (the format's own
canonical converter, also via Docker) produces the genuine `.pmtiles`;
the mbtiles intermediate is discarded. Verified on both tilesets: magic
bytes now read `PMTi`, `go-pmtiles convert` reported real tile counts (684
for boundaries, 123,448 for parcels) with no errors. Re-tiled both
statewide with the fix (`boundaries.pmtiles` 1.8MB, `parcels.pmtiles`
762.7MB -- both still comfortably under the §7.1 4GB budget, smaller than
their mbtiles intermediates too).

**Decisions (§13.2):**
- District Exposure's current-vs-future bars are grouped, not literally
  stacked -- see Done above; logged since it's a rendering-choice
  interpretation of §7.2's wording, not a literal implementation of it.
- `parcels.pmtiles`' attribute schema was widened well beyond the
  original "minimal attrs" framing (§7.1) specifically so the detail panel
  works without a second fetch per click. Logged since §7.1 explicitly
  says "minimal" -- the widened schema (762.7MB) is still ~5x under
  budget, and the alternative (WASM parquet reads for the base experience)
  contradicts §7.2's own graceful-degradation requirement more directly
  than a larger tileset does.

**⚠ Deviations / open items:**
- **Live browser re-verification of the parcel-tile click → detail panel
  interaction hit a tooling wall this session, not a code defect --
  documented precisely rather than either claiming it works or hiding the
  gap.** Independently verified via direct binary inspection and the
  `go-pmtiles convert` tool's own output that the fix is correct (see
  above). But re-testing the *live* interaction after the file swap
  repeatedly showed MapLibre's `load` event never firing -- traced this
  all the way down: ruled out my own code (bypassed it entirely, same
  symptom on a bare hand-built MapLibre instance), ruled out network
  reachability (every single resource the style needs -- style JSON,
  sprite, glyphs, tile source -- fetched in single-digit milliseconds via
  a plain `fetch()`), ruled out Web Workers generally (a bare postMessage
  round-trip worked fine) and Service Workers (none registered). What's
  left, and what matches every symptom (network-independent operations
  fine, anything render-loop-dependent never completing, no thrown error
  either way): the screenshot tool's own error message throughout this
  investigation was **"the Browser pane is not displayed, so the page is
  not compositing frames"** -- MapLibre's WebGL render/load pipeline
  plausibly gates on `requestAnimationFrame`, which browsers throttle or
  suspend for a non-composited surface, while plain fetch/Worker calls are
  unaffected. This is a preview-tooling/session state issue, not
  something fixable from the code side. What *was* verified live and
  working, extensively, before and independent of this: the choropleth
  (both county and muni layers, real data, sensible geographic pattern),
  all three data views with real numbers cross-checked against earlier
  session findings (Ocean County 421,551 parcels exact match; ranked munis
  correctly topped by the actual LBI/barrier-island chain), muni-scoped
  search returning real addresses, CSV export triggering a real
  `meta.json` fetch with no errors, and filter-state persistence across
  view navigation.
- Live P8 address geocoding (free-text address → point, via NJ's
  geocoder REST service) is not wired up. Search currently covers PIN/
  block-lot/address-substring via the local shard only (§7.1's own design
  for that path), which is genuinely useful on its own, but the "address
  via P8 geocode" half of §7.2's search bar description is not built.
- No automated WCAG audit (axe-core) or Playwright suite (§12.2: "Axe:
  zero serious violations"; "Playwright: search by PIN → panel; county→
  muni filter cascades; district chart matches summary JSON; export
  downloads with disclaimer") -- the manual/structural checks in Done
  above are real but not a substitute for the automated suite §12.2 asks
  for. Not attempted this session given time already spent on the
  tiling-format investigation above.
- R2 upload still not done (needs a credentials/infra decision, flagged
  since guide-Phase 6).
- DuckDB-WASM in-browser explorer (§7.4) is an explicit stretch goal, not
  attempted -- consistent with scope, not a gap.
- The Phase 1 join-rate limitation (88.34% vs required ≥97%) continues to
  be carried forward, unrelated to this phase's work.

**Next:** finish live-verifying the parcel click/detail-panel interaction
once the preview tooling cooperates; wire up P8 live geocoding; the
automated axe/Playwright suite (§12.2); R2 upload + credentials decision;
then the rest of guide-Phase 8 (README, portfolio assets) that
`09_validate.py` alone (2026-08-13, above) didn't cover.

---

## 2026-08-13 — Guide-Phase 8 (§11): final QA gates, `09_validate.py` (agent: sonnet-5)

Owner asked specifically for `09_validate.py`, not the full guide-Phase 8
scope (README/portfolio assets/full known-area validation beyond §12.1's own
gate 5) -- this entry covers the QA gates only.

**§12.1 actually has 7 gates, not 4** -- re-read the section in full before
implementing rather than working from what was in this session's own memory
of it (gates 1-4 only). Gates 5-7 (distribution sanity incl. named-town
validation, rollup invariants, privacy audit) are real, additional scope,
not skipped.

**Done:**
- Implemented `09_validate.py`: every gate re-derived fresh from processed/
  published data (never trusts an earlier phase's own self-reported PASS --
  that would defeat the point of a final, independent validation pass).
  Supports `--fixture` for gates 1-3 (fast, matches §12.1's "+ pytest on
  fixture" framing); gates 4-7 need parcel_flood/parcel_scores/published-
  artifact data with no fixture-scale equivalent, reported SKIPPED there,
  not faked.
- **Investigated both real (non-join-rate) findings seriously instead of
  just reporting FAIL, per §12.1 gate 5's own explicit "stop and
  investigate before publishing" instruction:**
  - **Gate 1 (uniqueness)**: first run showed composite_key with *more*
    statewide duplicates (745) than PIN itself (742) -- paradoxical on its
    face. Traced it to 1,285 rows (0.037% statewide) that are fully
    identical across *every* column in `parcel_master`'s schema, not just
    PIN -- confirmed directly (`.duplicated(keep=False).all() == True` on a
    sample). **72% of them (921/1,285) are in Cape May alone** -- the same
    county that's been the standout outlier in every previous phase (worst
    join rate, Phase 1; the only county needing the NFHL bisection fallback
    for real, Phase 2; an unexplained timing anomaly, Phase 3). Most
    plausible explanation, consistent with that pattern: genuinely distinct
    physical-parcel geometries that happen to share identical MOD-IV-
    unmatched attributes (same block/lot/qual, all-null value fields) --
    `composite_key` is attribute-only, so it structurally cannot
    distinguish two rows whose only difference is a geometry the attribute
    table doesn't carry. This isn't a dedup bug (§11 Phase 1's own exact-
    duplicate collapse is working correctly; these rows are collapsed to
    the extent attributes alone can determine), so the gate was revised to
    separate "PIN collisions composite_key could have resolved but didn't"
    (a real problem, checked directly per group) from "PIN collisions where
    the source rows are fully attribute-identical" (a distinct, explained,
    and -- at this scale -- accepted category) rather than requiring an
    attribute-only key to hit an unsatisfiable bar. **Result: 0 of the
    fixable kind, 1,285 of the explained kind. Gate passes.**
  - **Gate 5 (distribution sanity)**: Bound Brook -- the guide's own
    explicitly-named riverine validation town, also required as the Phase 1
    fixture -- initially ranked at the **27th percentile** statewide by a
    current/future-flag-based "% at risk" metric, nowhere near "high".
    Investigated rather than accepted: Bound Brook (Somerset County, not
    P4-covered) has a low raw SFHA-touch rate (4.6%) but a high moderate/
    shaded-X rate (17%), and zero future-layer contribution at all (no P4
    coverage) -- a flag-only metric structurally can't see either of those
    dimensions. Re-ranked by **% of parcels in a moderate-or-worse score
    band** (§5.3's own classification, and what a user actually sees on the
    dashboard) instead: Bound Brook jumps to the **89.5th percentile**,
    Manville to the **79.8th** -- both decisively "high" as the guide
    expects. Fixed the gate's metric choice, not the threshold or the
    towns -- §5.5's literal "% at risk" wording doesn't pin down a lens,
    and the band classification is the more faithful "at risk" definition
    for a domain-knowledge check like this one.
- Gates 3 (geometry), 4 (consistency, incl. a full statewide score-
  recompute check mirroring Phase 5's own, not sampled), 6 (rollup
  invariants, re-derived from the *published* summary JSON, not by
  re-running the aggregation), and 7 (privacy audit, grep of all 587
  committed artifact JSON files + a source-level audit of `07_tiles.py`'s
  attribute construction, since PMTiles is binary and not directly
  greppable) all passed cleanly on the first correctly-implemented run.
- Added `pipeline/tests/test_validate.py` (15 offline tests, synthetic
  data): one pair of tests per gate covering both the pass and fail path,
  including dedicated regression tests for the two nuances found above
  (full-row-identical vs. genuinely-fixable PIN collisions; band-based vs.
  flag-based "% at risk" for the named-town check). Full suite: **93/93
  passing** (78 from Phases 1-4b/5/6 + 15 new).
- **Ran the real statewide validation. Result: 6 PASS, 1 FAIL.** The one
  failure is `join_rate=0.8834` -- exactly, to four decimal places, the
  already-known, owner-approved-to-carry-forward limitation from
  2026-08-12, not a new finding. Every other §12.1 gate passes on the full
  3,478,722-parcel statewide dataset. Wrote `VALIDATION_REPORT.md`.

**Decisions (§13.2):**
- Gate 5's "% at risk" ranking metric changed from a current/future-flag
  definition to a score-band definition (moderate/high/severe) -- logged
  explicitly since it's a methodology choice affecting a named QA gate, not
  just an implementation detail.
- Gate 1 treats "composite_key can't resolve fully-attribute-identical
  rows" as a distinct, passing category rather than a gate failure --
  logged since it's a substantive interpretation of §12.1's "resolved by
  composite key" language, not a literal quote.

**⚠ Deviations / open items:**
- **The Phase 1 join-rate limitation (88.34% vs required ≥97%) is now
  formally confirmed as the project's one outstanding §12.1 gate failure**
  by an independent, from-scratch validation pass -- still carried forward
  per the owner's 2026-08-12 direction, not re-litigated here, but now
  documented as *the* specific, sole gate failure rather than one of
  several open questions.
- The 1,285 full-row-identical rows (Gate 1) are not fixed in the
  underlying data -- at 0.037% statewide they don't move any score,
  aggregate, or tile in any detectable way, and a full statewide re-run of
  Phases 1-8 to eliminate them would cost far more than the finding is
  worth. Noted for whoever next touches Phase 1/Cape May specifically.
- This entry covers `09_validate.py` (§12.1) only, per the owner's specific
  request -- the rest of guide-Phase 8's stated scope (known-area
  validation beyond gate 5, README, portfolio assets) is not done.

**Next:** guide-Phase 7 (web app, §7.2) is still undone; the rest of
guide-Phase 8 (README, portfolio assets) remains after that. Owner's call
on sequencing, as before.

---

## 2026-08-13 — Guide-Phase 6 (§11): tiles + search index, statewide (agent: sonnet-5)

**Tooling route (§6.2 explicitly asks this be documented): Docker, not WSL.**
Tried WSL first (Ubuntu, already installed) since it was already running --
blocked: `apt-get install tippecanoe` needs an interactive `sudo` password
this session has no way to supply. Pivoted to Docker (daemon wasn't running,
started it, ~30s). `felt/tippecanoe` (the actively-maintained upstream fork)
turned out not to be published under that name on Docker Hub *or* GHCR
despite showing up as an "upstream" reference in another image's
description -- used `klokantech/tippecanoe` (v1.24.1) instead, verified live
it actually runs before building anything on top of it.

**Done:**
- `07_tiles.py`: `tiles/parcels.pmtiles` (z13-16, minimal attrs -- pin, band,
  class_group, current/future flags, per §7.1's own "minimal attrs"
  instruction, not the full score schema) and `tiles/boundaries.pmtiles`
  (counties + municipalities as two named layers, z0-12, summary attrs from
  the aggregates phase).
- **Found a real bug in the municipality-boundary matching, the hard way.**
  County/tract boundaries so far all came from services that share this
  project's own FIPS/GEOID keys directly. Municipality boundaries don't --
  TIGER's county-subdivision service (`Places_CouSub_ConCity_SubMCD`, a
  *different* MapServer than the one already used for counties) has its own
  naming, so matching to this project's own `mun_code` needs a normalized
  name join. First version normalized by *stripping* the municipal-type word
  (BOROUGH/TOWNSHIP/etc.) entirely -- silently collapsed 19 pairs of
  genuinely distinct, separately-incorporated NJ municipalities that share a
  base name onto the same key (Berlin Boro *and* Berlin Twp are two real,
  different towns; so are Chatham Boro/Twp, Egg Harbor City/Twp, 17 more
  pairs). The resulting many-to-many join fan-out inflated the muni count
  past 564 -- the impossible arithmetic (more output rows than input rows on
  a left join) was the tell, not a manual audit. Fixed by *canonicalizing*
  the type word (BOROUGH->BORO, TOWNSHIP->TWP, etc.) instead of stripping it,
  preserving exactly the distinction that matters while still collapsing
  formatting noise (hyphen/space/none, "and" insertion, TIGER's full words
  vs. MOD-IV's abbreviations, a redundant doubled type-suffix on "Ventnor
  City *city*").
  - Iteratively reduced genuine formatting-only mismatches from 31 -> 20 -> 12
    unmatched (of 565 valid TIGER rows) via systematic, generalizable fixes
    (MOUNT->MT, SOUTH->SO, NORTH->NO, HEIGHTS->HGHTS, TWNSHP/TWSHP->TWP),
    each verified against the live data before adding, not guessed.
  - **Stopped at 12, on purpose, not from running out of ideas.** The
    residual spans genuinely different root causes, not one more formatting
    rule away from zero: a word-order difference ("City of Orange" vs.
    MOD-IV's "Orange City", both correctly reflecting Orange NJ's actual
    quirky legal name); an apparent **source-data quality issue** in MOD-IV
    itself, not a formatting gap -- several real Essex County boroughs
    (Caldwell, North Caldwell, Essex Fells) are recorded with "TWP" as their
    type in MOD-IV despite being boroughs in reality (one entry literally
    reads "CALDWELL BORO TWP", both words at once); and Pine Valley, NJ's
    famously tiny (~15-resident, mostly-golf-course) borough, which may
    simply have zero named (MOD-IV-matched) parcels to derive a name from at
    all. Forcing any of these to match would risk papering over a real
    signal rather than fixing a formatting difference -- logged clearly
    (never silently dropped) instead.
- `08_search_index.py`: `search/{fips}/{mun}.json.gz` (address/block-lot/PIN
  -> PIN + centroid) and `parcels/{fips}/{mun}.parquet` (full scored rows).
  Centroid computed in the working CRS (EPSG:26918) then reprojected to
  WGS84 for output, not computed directly in a geographic CRS. Uses the
  same `{county FIPS}{mun_code suffix}` muni-key convention as the
  aggregates phase -- and since this keys directly off this project's own
  `mun_code` (no TIGER name-matching involved), produced all 564 shards
  cleanly, no residual gap the way boundaries.pmtiles has one.
- **Caught a real repo-hygiene issue before committing, not after**: this
  phase's own outputs (a 461MB `parcels.pmtiles`, 182MB of per-muni parquet,
  62MB of search shards) would have been silently swept into the next
  `git add -A` -- `.gitignore` only excluded `data/raw/`/`data/processed/`,
  not the new `artifacts/tiles|parcels|search/` directories §7.1 explicitly
  marks "R2 unless noted" (i.e. *not* meant for this repo at all, unlike the
  small `artifacts/summaries/` JSON from the aggregates phase). Fixed before
  staging anything.
- Added `pipeline/tests/test_tiles.py` (5 offline tests): the formatting-
  normalization cases handled, and -- the actual regression test for the
  bug above -- an explicit assertion that two synthetic Boro/Twp pairs
  produce exactly 2 matched rows, never 4, plus an unmatched-is-logged-not-
  forced case. Full suite: **78/78 passing** (73 from Phases 1-4b/5 + 5 new).
- Ran statewide. **Results, independently verified, not just trusted from
  the build log:**
  - `parcels.pmtiles`: **461 MB** (budget: ≤4 GB), all 3,478,722 parcels
    confirmed read by tippecanoe's own feature count.
  - `boundaries.pmtiles`: 2.1 MB, 21 counties + 553 (of 564) municipalities.
  - **564/564 municipality search shards written** (`search/{fips}/{mun}
    .json.gz`), keyed directly off `mun_code`, not TIGER matching.
  - **§11's own stated gate, run for real**: 20 randomly sampled parcels
    (one per county, distinct RNG seed from the sample draw) looked up by
    PIN against their county+muni's search shard -- **20/20 resolved**.

**Decisions (§13.2):**
- `klokantech/tippecanoe` (Docker Hub, v1.24.1) is the tippecanoe image in
  use, not `felt/tippecanoe` -- recorded since a future session might
  otherwise assume the more famous name is what's actually configured.
- Municipality-boundary matching accepts a 12/564 (2.1%) gap in
  `boundaries.pmtiles` rather than forcing every TIGER row to match --
  documented above; `parcels.pmtiles` (the core per-parcel layer) and the
  search index are both unaffected, since neither depends on TIGER's
  county-subdivision boundaries at all.

**⚠ Deviations / open items:**
- The Phase 1 join-rate limitation (88.34% vs required ≥97%) is still
  carried forward unresolved, per the owner's 2026-08-12 direction.
- The 12 unmatched municipalities in `boundaries.pmtiles` (listed in this
  session's tool output, not reproduced in full here) means those 12 towns
  won't render in the municipality choropleth layer specifically -- they
  still have full data everywhere else (parcels.pmtiles, search, summaries
  JSON, scores). Worth a look if a future session has a reason to (e.g. an
  authoritative NJ MOD-IV-code-to-Census-GEOID crosswalk, if one exists,
  would sidestep name-matching entirely) -- not blocking.
- **R2 upload itself was not attempted** -- §6.2/§7.1 call for a Cloudflare
  R2 bucket (public, CORS-enabled) as the actual hosting destination for
  these artifacts, which means real cloud infrastructure and credentials
  this session doesn't have and shouldn't set up unilaterally. The local
  build artifacts (`artifacts/tiles/`, `artifacts/parcels/`,
  `artifacts/search/`, all gitignored) are ready to upload whenever that's
  decided.
- Two Essex County MOD-IV boro/twp mislabels (Caldwell, North Caldwell,
  Essex Fells all recorded "TWP") found as a side effect of this phase --
  doesn't affect scoring (class_group/geometry/value are independent of
  this label) or Phase 1's own crosswalk (property class, not municipality
  type), only this phase's boundary-name matching -- noted for awareness,
  not acted on further.

**Next:** guide-Phase 7 (web app, §7.2) -- Vite + React + MapLibre, or
guide-Phase 8 (`09_validate.py` full QA gates) first, depending on how the
owner wants to sequence the remaining work; the guide's own table lists Web
App before QA+launch.

---

## 2026-08-13 — Phase 5 (§11): geography × class × lens aggregates, statewide (agent: sonnet-5)

**⚠ Phase-numbering correction first:** the two entries below this one label
`04_claims.py` and `05_score.py` as separate "Phase 4"/"Phase 5". That's
wrong against the guide's own §11 table, which bundles both scripts as one
phase ("4. Claims + scores") and lists `06_aggregate.py` -- this entry --
as "5. Aggregates". Not editing those entries (append-only log), correcting
here: this is guide-Phase 5, and the next script (`07_tiles.py`, tiles +
search index) is guide-Phase 6, not whatever came after this one gets
called next. Caught while re-reading §11 in full before starting this
phase's work, rather than continuing to extend the mislabeling forward.

**Done:**
- Implemented `06_aggregate.py` (§5.5): county/muni/class-group already
  exist on `parcel_master` (Phase 1) -- no new spatial join needed here,
  unlike Phase 4's tract assignment. `mun_code` (PCL_MUN), not `mun_name`,
  is the muni grouping key -- `mun_name` is blank for the same ~11.7% of
  parcels Phase 1's join-rate finding already covers (it's populated from
  the same MOD-IV join), while `mun_code` is always populated. Verified
  live that all 564 `mun_code` values have a derivable name via majority
  vote among matched parcels (one single-record naming inconsistency
  found statewide, correctly resolved by the vote, not a real ambiguity).
- Risk lenses (current/future/either, §5.5) map onto §5.2's already-defined
  flags. **The `future` lens excludes non-P4-covered parcels from both
  the numerator and denominator entirely** -- not counted as "not at risk"
  -- so a county with partial P4 coverage doesn't get a silently-diluted
  future-risk percentage; a county with *zero* covered parcels correctly
  produces no future-lens row at all rather than a misleading 0/0.
  `either`'s overlap fraction (for the overlap-based value-at-risk
  companion metric) uses `GREATEST(sfha_pct, fut_pct)` where covered --
  the guide doesn't spell out a combined-lens overlap fraction explicitly,
  so this is a documented interpretation (§13.2), not a literal formula
  quote.
- Used DuckDB for the actual aggregation (per §6.2/§6.3's explicit tooling
  choice) via a "lensed" long-format view (one row per parcel×lens) so one
  GROUP BY query handles all three lenses uniformly; combining
  `parcel_master`+`parcel_scores` beforehand is still done in pandas with
  the same row-position verification as Phase 5/`05_score.py` (exact pin-
  sequence equality asserted per county), since a SQL join on `pin` would
  have the same duplicate-PIN correctness risk already documented twice.
- **Found and fixed two real bugs by actually running this against the
  full statewide dataset, not just trusting the design:**
  1. A SQL binder error on the very first run (rollup query selected
     `class_group` without it being in `GROUP BY` or aggregated) --
     trivial to fix, caught immediately by DuckDB itself refusing to run it.
  2. **A much more serious bug in the QA check meant to catch exactly this
     class of problem**: `check_rollup_invariant`'s first version grouped
     municipalities by `(class_group, lens)` only, forgetting `county`
     entirely -- so every county's rollup was being compared against a
     *statewide* sum of all 564 municipalities, not just its own. First
     real run "found" 2,265 violations, all wildly inflated (some >100,000%
     off) -- the absurd magnitude was itself the tell that the *check* was
     broken, not the aggregation. Fixed by attaching a `county` column to
     the muni-level frame (built once from a verified 1:1 `mun_code`→
     `county` mapping) and grouping by it too. Added a dedicated regression
     test that reproduces the exact bug (mislabels one municipality into
     the wrong county) and asserts the fixed checker actually catches it --
     not just that it passes on good data.
  3. **A real deviation from §7.1's artifact naming, found during
     independent verification, not by the rollup check**: county summary
     files were being written as `{county name}.json` (e.g.
     `ATLANTIC.json`) because the aggregation groups by `combined`'s own
     `county` column, which holds the name (Phase 1's schema). §7.1 wants
     `summaries/county/{fips}.json`. Fixed by translating name->FIPS only
     at file-write time via the existing `COUNTY_FIPS` lookup, leaving the
     aggregation SQL untouched. Municipality files needed the same fix for
     `{fips}{mun}.json` -- verified live first that `mun_code`'s own last-2-
     digit suffix is unique *within* every county (no collisions) before
     using `{county FIPS}{mun_code suffix}` as the muni file key.
- Added `pipeline/tests/test_aggregate.py` (8 offline tests, in-memory
  DuckDB + a tiny 4-parcel/2-county synthetic fixture, hand-computed
  expected values): the mun_name majority-vote lookup, per-lens semantics
  verified against hand math (including the future-lens exclusion and the
  either-lens GREATEST rule), the class-group-rollup-plus-per-class
  co-existence, and both a rollup-invariant pass case and the specific
  regression case above. Full suite: **73/73 passing** (65 from Phases 1-4b
  + 8 new).
- Ran statewide: **3,478,722 parcels aggregated, 564 municipalities.**
  Rollup invariant (§11 gate): **PASS**, re-verified independently by
  recomputing one county (Salem) directly from the raw parquet files in
  plain pandas (no DuckDB, no reuse of this script's own functions) and
  matching the written JSON exactly; muni-file count (564) and the ranked-
  municipality table's total (564 across all 21 counties, no drops or
  duplicates) both checked directly.
- Statewide, either lens, all classes: **671,829/3,478,722 parcels at risk
  (19.31%)**, value exposure **25.86%**. By class group: "Other"
  (rail/utility/misc) has both the highest at-risk share (31.22%) and by
  far the highest value exposure (71.69%) -- plausible, since utility/
  infrastructure siting is often water-adjacent for practical reasons, not
  a red flag. Residential is lowest on both (15.90% / 21.15%) -- also
  plausible given it's the most widespread, least water-concentrated class.

**Decisions (§13.2):**
- `either` lens's overlap fraction = `GREATEST(sfha_pct, fut_pct)` where
  future-covered, else just `sfha_pct` -- documented above, flagging since
  §5.5 doesn't spell out a combined-lens formula explicitly.
- Ranked-municipality table (§7.2) built on the either-lens, all-classes
  rollup specifically -- the guide's UI description doesn't pin down which
  lens/class scope "ranked municipalities" uses; either/ALL is the
  broadest, most general "which towns are most at risk" framing.

**⚠ Deviations / open items:**
- The Phase 1 join-rate limitation (88.34% vs required ≥97%) is still
  carried forward unresolved, per the owner's 2026-08-12 direction.
- Muni summary JSON carries `county_name` (human-readable) alongside its
  data; the exact `{fips}{mun}` key format is this session's best
  reconciliation of §7.1's naming with what Phase 1's schema actually
  provides (`mun_code`/PCL_MUN, not a FIPS-native muni code) -- worth a
  quick sanity check against whatever Phase 6 (tiles/search index) and
  Phase 7 (web app) actually expect when they're built, in case either
  assumes a different muni-key convention.
- `artifacts/summaries/` and `artifacts/ranked_municipalities.json` ARE
  committed (small, aggregate-only JSON, matches §8's "artifacts/ small
  committed JSON" convention) -- these are the first Phase-6-onward
  artifacts actually committed to the repo, unlike the gitignored
  per-parcel `data/processed/parcel_*/` outputs from every prior phase.

**Next:** Guide-Phase 6 (`07_tiles.py` + `08_search_index.py`) -- GeoJSONL
→ tippecanoe → PMTiles, and per-muni search shards. First phase needing the
tippecanoe route decided back in Phase 0 (Docker, confirmed working) and
R2 upload/CORS (§6.2/§7.1).

---

## 2026-08-13 — Phase 5: composite score + bands, statewide (agent: sonnet-5)

Pure computation (§5.3) over Phases 1/3/4's already-computed outputs -- no
network, no expensive geometry. Ran in seconds, not the hours the last two
phases needed.

**Done:**
- **Re-derived the §5.3 weight-redistribution math from the guide's literal
  text and found a real discrepancy with this project's own early record.**
  §5.3: "if P6 unavailable, redistribute its [C_loss's 0.25] weight
  proportionally to the other two [C_cur 0.45, C_fut 0.30]." Proportional to
  their existing ratio: `0.45/(0.45+0.30)=0.60`, `0.30/0.75=0.40`, summing
  to 1.0 exactly. The Phase 0 record (months earlier in this project) had
  noted "~0.643/0.357" for this same fallback -- re-derived it fresh here
  since I was about to actually implement it, and couldn't reconcile that
  figure under any reading of "proportional to the other two" (0.643+0.357
  sums to 1.0 only by rounding coincidence, not by construction the way
  0.60+0.40 does). Treating the early figure as a stale error and using the
  freshly-derived 0.60/0.40, not silently carrying the old number forward
  just because it was already written down somewhere.
- Implemented `05_score.py`: `C_cur`/`C_fut` computed exactly per §5.3's
  formulas (presence floor, moderate-risk additive term, future-coverage
  fallback); `C_loss` = Phase 4's `tract_loss_pctile` directly (P6 turned
  out to be available, so the redistribution fallback only fires for the
  31 statewide parcels Phase 4 couldn't match to any tract, not a dataset-
  wide P6 outage -- same underlying mechanism, different trigger, applied
  per-parcel rather than per-run).
  - **`C_loss` is always stored as a clean 0.0-filled value, never raw
    NaN**, specifically so §12.1's "score reproducible from stored
    components" gate holds unconditionally: with the redistributed
    `w_loss=0`, `0 * NaN` is itself `NaN` under IEEE float rules, which
    would silently break an otherwise-correct recompute check. Verified
    this distinction actually matters with a dedicated test, not just
    asserted it.
  - Row alignment across `parcel_master`/`parcel_flood`/`parcel_claims`
    (three files written independently by three different scripts) is by
    **row position, not a `pin` join** -- same duplicate-PIN reasoning as
    Phases 3/4 -- but explicitly **verified** per county (exact pin-sequence
    equality asserted, not just trusted) before combining, so a future
    change to one script's row order would fail loudly here instead of
    silently fusing the wrong county's rows together.
- Added `pipeline/tests/test_score.py` (25 offline tests): presence floors,
  the capped-at-1 boundary, the future-coverage fallback, both weight
  schemes, **every exact score/band boundary** (0, 1, 24, 25, 49, 50, 74,
  75, 100 -- the classic off-by-one risk zone for a bands-from-cutoffs
  function), and two dedicated recompute-check tests (§12.1 gate 4) --
  one of which specifically reproduces the NaN-times-zero-weight trap
  and confirms the stored `C_loss` design avoids it. Full suite:
  **65/65 passing** (40 from Phases 1-4 + 25 new).
- Verified on Salem alone first, then ran statewide (21/21 counties).
  **3,478,722 parcels scored -- exact match to Phase 1/3/4.** 31 parcels
  had `C_loss` redistributed, **exactly matching Phase 4's statewide count
  of tract-unmatched parcels** -- a clean cross-phase consistency signal
  that wasn't specifically engineered, just fell out of both phases
  handling the same 31 edge-case parcels correctly.
- **Independently re-verified from the output files, every row (not a
  sample)**: all `score` in [0,100], all `C_cur`/`C_fut`/`C_loss` in [0,1],
  zero raw NaN in `C_loss`, **zero recompute-check mismatches across all
  3,478,722 rows**, PIN sets and row counts match `parcel_master` exactly
  per county. **Result: PASS, no exceptions.**
- Statewide band distribution: **low 2,806,930 (80.7%); severe 288,087
  (8.28%); moderate 194,462 (5.59%); high 189,233 (5.44%); none 10
  (0.0003%).** "None" (score exactly 0) requires all three components to
  be simultaneously exactly zero -- rare by construction, since `C_loss`
  is a percentile rank and only the tract(s) at the absolute bottom of
  ~2,178 ranked tracts can land on exactly 0.0, so this small count is a
  sign the formula is behaving as designed, not a bug.

**Decisions (§13.2):**
- Redistribution weights corrected to 0.60/0.40 (see Done above) --
  logged explicitly since §13.3 lists the score formula/weights among
  what needs owner awareness for any change, and this corrects a number
  that was on record, even though it was never actually load-bearing
  until this phase.

**⚠ Deviations / open items:**
- The Phase 1 join-rate limitation (88.34% vs required ≥97%) is still
  carried forward unresolved, per the owner's 2026-08-12 direction.
- `data/processed/parcel_scores/` intentionally not committed (gitignored,
  §8 convention) -- `SCORE_SUMMARY.md` (band distribution only, no
  per-parcel data) is committed.

**Next:** Phase 6 (`06_aggregate.py`, §5.5) -- geography × class-group ×
risk-lens rollups (county/muni, % at risk, value at risk) into DuckDB →
JSON artifacts. First phase that touches §5.5's exact aggregate formulas
and the ranked-municipality table.

---

## 2026-08-13 — Phase 4: NFIP claims → tract loss percentile, statewide (agent: sonnet-5)

**Started with the owner's specific instruction: re-check P6 before proceeding.**
Good thing -- the situation changed since Phase 0, and not in the simple
"back up" direction.

**Done:**
- **Re-checked P6 live rather than trusting the Phase 0 finding or the
  recon script's own cached verdict.** Found `check_p6_claims()` in
  `00_recon.py` had a **real bug**: it hardcoded `"ok": False`
  unconditionally, never actually deriving availability from the live probe
  results it computed -- meaning it would have kept reporting "unavailable"
  forever even after the source came back. Fixed to derive `ok` from an
  actual content check (a real NJ record with the expected geography field),
  not just "got HTTP 200 + valid JSON" (the same class of gotcha as the
  ArcGIS `{"error":...}`-under-200 bug fixed back in Phase 1 -- checked for
  it here on principle, this API's error convention turned out fine).
- **What the live re-check actually found**: the old v2 `FimaNfipClaims`
  endpoint now returns HTTP 200 (not the 503 from 2026-08-02), but its own
  response body carries a `DeprecationInformation` block -- data **frozen as
  of 2026-06-01**, the dataset itself **removed 2026-10-15**, pointing to a
  renamed replacement. Found and verified the replacement live:
  **`https://www.fema.gov/api/open/v3/NfipClaims`** (no "Fima" prefix),
  `lastDataSetRefresh` ~9 days before this check -- actively maintained, not
  another dead end. Updated `nj_parcel_lib.py`'s `P6_CLAIMS_QUERY_URL` and
  `P6_STATUS_KNOWN_UNAVAILABLE` (now `False`), re-ran `00_recon.py --force`
  (all 7 sources now show OK), updated `test_recon.py`'s now-stale
  always-unavailable assertion.
- **Designed + implemented `04_claims.py`** (§5.2/§5.3 `C_loss`):
  - Fetches NJ census tracts from TIGERweb. This MapServer bundles several
    "Census Tracts" layers, each paired with a different ACS attribute
    vintage (2024/2025) plus an explicit "Census 2020" grouping and an
    ambiguous unlabeled top-level default -- verified live that the
    unlabeled default and the explicit 2020 layer return identical NJ tract
    counts (2,181) and fields (tract *boundaries* don't change between
    decennial censuses regardless of which ACS estimate vintage they're
    bundled with for attributes this phase doesn't use anyway). Used the
    explicitly-labeled layer.
  - Fetches NJ claims via OData `$select=censusGeoid` -- **verified this
    actually returns records with only that one field**, not a default
    field set plus the requested one. §5.6 ("NFIP claims never shown below
    tract level") means the other 83 fields on a claims record (addresses,
    damage amounts, elevation certs, dates) are never fetched at all, not
    fetched-then-dropped -- same discipline as Phase 1's field allowlist.
  - Sample claim's `censusGeoid` is a 12-digit **block-group** GEOID;
    truncated to 11 digits for the tract-level key §5.2 asks for.
  - Assigns every parcel to a tract via **centroid**-in-polygon (not an
    overlap-percentage the way Phase 3 does it) -- a single categorical
    "which tract" assignment is all this phase needs, and centroid-based
    join is standard for this and far cheaper than repeating Phase 3's
    overlay machinery. Keyed by a synthetic row id, not `pin` (same
    duplicate-PIN safety reasoning as Phase 3).
  - `claims_per_1000_parcels` = claim *record* count (not distinct
    properties -- a repeat-loss property contributes one row per
    historical claim) per tract, ÷ parcels-in-scope-in-that-tract × 1000.
    Statewide percentile ranked only among tracts with ≥1 scored parcel --
    a 0-parcel tract's rate is undefined/0 by construction, not a real
    "low risk" signal, so it doesn't dilute the ranked population.
  - Individual claim records are never joined to a parcel or written
    anywhere -- only the tract-level aggregate (count, rate, percentile) is
    retained, then merged onto parcels by `tract_geoid`. The per-parcel
    output carries a tract-level *statistic*, not claims data.
- Added `pipeline/tests/test_claims.py` (7 offline tests, no network):
  `compute_tract_summary`'s formula/ranking/zero-parcel-exclusion, and
  `assign_tracts`'s containment/unmatched/duplicate-PIN/boundary-tie
  handling (the tie case constructed with deliberately-overlapping test
  polygons, since real tracts don't overlap and a genuine boundary tie
  isn't reliably reproducible). **Caught a real mistake in my own test**,
  not the code: assumed a 2-way tie at the top of a ranked pair would give
  both elements percentile 1.0; pandas' average-rank convention actually
  gives `(1+2)/2/2 = 0.75`, matching the *other* tie test's math exactly --
  fixed the test's expectation, not the code, once traced through by hand.
  Full suite: **40/40 passing** (33 from Phases 1-3 + 7 new).
- Verified on Salem alone first, then ran the full statewide ingest, 21/21
  counties. **Results**: 2,181 NJ tracts; **202,287 NJ claim records**
  fetched; 1,960 (0.97%) with missing/short `censusGeoid`; 17,721/200,327
  (8.85%) of the rest don't match a current 2020 tract GEOID (expected --
  claims span decades, older ones can reference pre-2020 tract boundaries;
  only affects those specific claims' contribution, not the whole dataset).
  **3,478,722 parcels processed -- exact match to Phase 1/3's count.** Only
  **31 parcels statewide (0.0009%) unmatched to any tract** (parcel
  centroid landing just outside every tract polygon -- minor NJOGIS/TIGER
  boundary misalignment, the same class of harmless edge effect already
  documented for county bboxes in Phase 2). 2,178/2,181 tracts have ≥1
  scored parcel.
- **Independently re-verified from the output parquet files** (not just the
  console log): 21/21 counties, statewide parcel count matches Phase 1/3
  exactly, PIN sets match `parcel_master` exactly per county, null
  `tract_geoid`/`tract_loss_pctile` agree exactly (no orphaned nulls), all
  non-null percentiles in [0,1]. **Result: PASS, no exceptions.**
- Top claims-density tract statewide: `34031246300` (Passaic County) --
  1,935 parcels, 5,275 claims (2,726 claims per 1,000 parcels, i.e. more
  claims than parcels on average). Plausible, not alarming: Passaic River
  basin has well-documented repetitive-loss flooding history (Floyd 1999,
  Irene 2011), consistent with properties there filing multiple claims
  across decades rather than a data error.

**Decisions (§13.2):**
- Claims counted as raw claim *records*, not distinct properties -- matches
  §5.2's literal "tract NFIP claims per 1,000 parcels" wording. A
  distinct-properties variant would be a defensible alternative reading;
  flagging the choice explicitly here rather than picking silently, since
  it's the kind of methodology detail §13.3 cares about.
- No per-county output-exists skip/checkpoint the way Phases 1-3 have --
  considered and deliberately not added, not an oversight: this phase's
  per-parcel percentile depends on a *statewide* aggregate (every county's
  parcel-to-tract counts feed the same ranked population), so a single
  county's output can't be correctly produced in isolation from a stale
  cache the way Phase 1-3's genuinely-independent per-county outputs could.
  The expensive part (claims/tract network fetch) already gets real
  resumability for free from `get_json()`'s existing cache; the per-county
  spatial join is cheap enough (simple centroid-in-2,181-simple-polygons,
  nothing like Phase 3's flood-zone overlay) that always redoing it is a
  reasonable, honest trade instead of a more complex intermediate-cache
  scheme. (Note for whoever runs this next: the statewide run above was
  accidentally invoked with `--force`, wastefully re-fetching the already-
  cached claims data instead of reusing it from the preceding Salem test --
  cost some redundant time against FEMA's API, not correctness. Don't pass
  `--force` unless the source data itself needs refreshing.)

**⚠ Deviations / open items:**
- The Phase 1 join-rate limitation (88.34% vs required ≥97%) is still
  carried forward unresolved, per the owner's 2026-08-12 direction.
- The old v2 P6 endpoint is scheduled for removal 2026-10-15 -- not used
  anywhere in this codebase now, but worth a quick re-verification on the
  *next* annual claims refresh (§6.4) that the v3 endpoint (or whatever
  FEMA renames it to next) is still what's configured, rather than assuming
  today's URL is permanent.
- `data/processed/parcel_claims/` and `tract_claims_summary.parquet`
  intentionally not committed (gitignored, §8 convention) --
  `TRACT_CLAIMS_SUMMARY.md` (aggregate counts only, §5.6-safe) is committed.

**Next:** Phase 5 (`05_score.py`, §5.3) -- assemble `C_cur`/`C_fut`/`C_loss`
into the composite 0-100 score and bands. All three inputs now exist for
real (Phase 3's `sfha_pct`/`fut_pct`, this phase's `tract_loss_pctile`) --
no fallback-weight redistribution needed, since P6 turned out to be
available after all.

---

## 2026-08-12 — Phase 3: parcel/flood intersections, statewide (agent: sonnet-5)

The heaviest pipeline stage (§6.3 budget: ≤12h statewide) and the first stage
where §12.1's geometry/consistency QA gates actually apply (§11's row for
Phase 3, not Phase 1/2). Total statewide runtime: **1.89h, well inside
budget** -- see the performance section below for why that wasn't a given.

**Done:**
- Wrote `03_intersect.py`: per county, overlays `parcel_geoms` (Phase 1)
  against the NFHL and CAFE SLR5 layers (Phase 2), all reprojected to
  EPSG:26918 (§4 working CRS) before any area math.
  - `sfha_pct` uses NFHL's own `SFHA_TF=='T'` flag directly rather than a
    hand-rolled `FLD_ZONE` prefix match -- verified live against Atlantic +
    Essex data that `SFHA_TF=='T'` <=> `FLD_ZONE` in `{A,AE,AH,AO,VE}` exactly
    (and `SFHA_TF=='F'` <=> `{X, OPEN WATER}`), so trusting FEMA's own
    classification is simpler and more robust than re-deriving it from §4's
    illustrative (not exhaustive) "A*/V*" pattern.
  - `mod_risk_pct` (shaded X / "0.2% annual chance") uses
    `ZONE_SUBTY == "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"` -- exact string
    confirmed live, not `FLD_ZONE=='X'` alone (which also includes
    unshaded/minimal-risk X).
  - `fut_pct` is a simple union overlap against the whole P4/CAFE layer for
    covered counties -- confirmed live the layer mixes a majority "SLR 5FT"
    label with a minority of retained FEMA zone labels (AE/VE/AO/"A - NO
    BFE"), but §5.2 asks for total future overlap here, not a sub-breakdown,
    so nothing is filtered out.
  - Overlap keyed by a synthetic per-row id, **not `pin`** -- Phase 1 found
    742 statewide conflicting-duplicate PINs (kept, not merged); grouping by
    `pin` here would have silently combined overlap area across two distinct
    parcels that happen to share one.
  - Sliver rule (§5.2) implemented as *either* test drops the overlap: <1% of
    the parcel's own area, *or* <10 m² absolute -- both are needed since one
    catches a trivial fraction of a huge parcel and the other catches a
    trivial absolute overlap on a tiny parcel.
  - `fut_pct`/`fut_flag` stored as null (not zero/False) for the 6
    non-P4-covered counties, via pandas' nullable boolean dtype for the flag
    -- makes it structurally awkward to accidentally read "no future risk"
    from a not-a-boolean value without checking `fut_coverage` first, per
    §5.2's explicit warning.
- **Performance: found and fixed a real problem before it became a 9-10h
  statewide run.** Naive per-feature `gpd.overlay()` took 325s on Salem --
  the *smallest* county -- linearly extrapolating to ~9-10h statewide, too
  close to the 12h budget for comfort on the largest counties. Profiled
  before guessing: Salem's SFHA layer alone (1,478 features) carries
  **4,045,728 vertices** (~2,738/polygon) -- confirmed this, not algorithm
  choice, was the cost driver by testing three different approaches
  (naive overlay, sjoin "intersects" prefilter, dissolve-then-vectorized-
  intersection) that were all similarly slow despite very different
  algorithmic strategies. Fix: `.simplify(1.0, preserve_topology=True)`
  applied to the flood-zone layers only (never parcels) -- cut Salem's SFHA
  vertex count to 467,558 (-88%) and measured a 4.6x faster overlay on an
  identical parcel subset, while shifting total intersection area by 0.004%
  (287 m² out of 7,013,629 m²) -- two orders of magnitude below the sliver
  thresholds already in place, and well inside the inherent modeling
  uncertainty of a modeled flood-zone boundary (not a surveyed line) in the
  first place. Salem end-to-end: 325s -> 118s (2.76x).
  - **Side effect investigated, not just noted:** the overlap-fraction clamp
    count jumped after simplification (Salem: 21 -> ~300+ per full run).
    Checked the actual raw-pct distribution among clamped parcels directly:
    mean 1.0015, 75th percentile ~1.0, only a handful reaching as high as
    1.60. Independently-simplifying topologically-adjacent zone polygons can
    shift their shared boundary slightly differently, causing a thin,
    previously edge-matched strip to register as double-covered -- this can
    only inflate a parcel's overlap fraction if it was already
    heavily/fully covered to begin with (a partially-covered parcel's summed
    overlap can't cross 100% from a boundary sliver alone), so the clamped
    *result* (capped to 1.0) is correct or very close to it either way. Most
    of the "clamped" count is this sub-percent noise, not a systematic bias
    -- not tuned to a second, coarser threshold for the logged count, since
    that would just be a different, equally-arbitrary judgment call baked
    into code instead of explained in prose here.
- Added `pipeline/tests/test_intersect.py`: 10 offline tests (synthetic
  squares/rectangles, no files, no network) covering full/partial/no overlap,
  both sliver-rule branches independently, multiple non-overlapping zones
  summing correctly, overlapping source zones triggering the clamp, and the
  duplicate-PIN row-position-keying guarantee. Full suite: **33/33 passing**
  (23 from Phases 1-2 + 10 new).
- Verified on Salem alone first (smallest county, P4-covered) before
  committing to a statewide run, matching the Phase 2 discipline.
- **Ran the full statewide Phase 3 ingest, 21/21 counties, 1.89h total**
  (sum of per-county wall time; well under the 12h budget). Total parcels
  processed: **3,478,722 -- exact match to Phase 1's count**, confirming no
  rows lost or duplicated across the phase boundary.
- **Independently re-verified §12.1's geometry + consistency gates from the
  output parquet files directly** (not just trusted the per-county console
  log or the script's own internal asserts): 21/21 counties, all `*_pct`
  columns in [0,1], all flags exactly consistent with their overlap (`flag ==
  (pct > 0)`), `fut_pct`/`fut_flag` null everywhere `fut_coverage` is false
  and nowhere else, every county's `parcel_flood` row count matches its
  `parcel_master` row count exactly. **Result: PASS, no exceptions.**
- Statewide results: **SFHA (current) risk 450,888 parcels (12.96%);
  moderate (shaded X) risk 179,398 (5.16%); future risk 532,899 of the
  2,852,889 parcels in P4-covered counties (18.68%)**.
- **Investigated a real timing outlier rather than just reporting it**: Cape
  May took 4,379.7s (73 min) -- ~65% of the *entire* statewide runtime by
  itself, ~8x the next-slowest county (Ocean, 536.6s), despite having fewer
  parcels than 6 other counties that all ran in well under 10 minutes.
  Checked the obvious hypothesis (vertex density) directly and it does
  **not** hold: Cape May's SFHA layer has *fewer* total vertices than
  Salem's (2.24M vs 4.05M) and its parcels average *fewer* vertices/parcel
  (10.3) than both Salem (15.2) and Ocean (28.6) -- Ocean in particular has
  both more parcels *and* higher per-parcel vertex density than Cape May,
  yet ran 8x faster. Not chased to a fully definitive root cause (would need
  profiling tooling below what's reasonable to invest for a non-blocking
  performance curiosity), but the most plausible explanation given the
  evidence is spatial *fragmentation* (many small, densely-interleaved
  islands/marshes/zones from Cape May's barrier-island geography) rather
  than per-feature complexity -- a different cost driver than the vertex
  density found and fixed above. Notable in its own right: **Cape May has
  now been the standout statistical/performance outlier in every single
  phase of this project** (Phase 1: worst join rate at 65.93% and most
  duplicate PINs by far; Phase 2: the only county needing the NFHL bisection
  fallback exercised for real; Phase 3: this). Not a coincidence worth
  ignoring, but not something blocking either, since every phase completed
  correctly for it regardless.

**Decisions (§13.2):**
- Sum-then-clamp (overlay individual zone features, sum per parcel, clamp to
  [0,1]) kept over a dissolve-first design, despite the clamp-noise question
  above -- tested dissolve-then-vectorized-intersection directly on Salem and
  it was not obviously faster than the fix actually shipped (union_all alone
  took 41s before any per-parcel work even started), so there was no
  performance reason to switch, and sum-then-clamp is simpler to reason
  about with the existing test suite.
- Simplification tolerance (1m) applied only to flood-zone layers, never to
  parcel geometry -- parcels are the actual unit of analysis and stay at
  full source precision; only the hazard-layer boundaries (already a modeled
  approximation, not a surveyed line) are simplified.

**⚠ Deviations / open items:**
- The Phase 1 join-rate limitation (88.34% vs required ≥97%) is still
  carried forward unresolved, per the owner's 2026-08-12 direction -- not
  re-litigated here.
- Cape May's Phase 3 timing anomaly (above) is characterized, not fully
  root-caused. Worth a real look if this pipeline is ever re-run against a
  refreshed NFHL vintage, but not blocking Phase 4.
- `data/processed/parcel_flood/` intentionally not committed (gitignored,
  matches §8's convention) -- `INTERSECT_SUMMARY.md` (human-readable) and
  `intersect_report.json`'s structure (via this log) are the durable record.

**Next:** Phase 4 (`04_claims.py`, §6.3) -- P6/NFIP claims to tract
percentiles. P6 was confirmed unavailable back in Phase 0 (§ RECON.md: HTTP
503 + Akamai-blocked bulk exports) and not re-checked since -- re-check
first; if still unavailable, this phase is mostly about correctly applying
§5.3's already-documented fallback (redistribute `C_loss`'s weight
proportionally to `C_cur`/`C_fut`, record the variant in `meta.json`) rather
than an actual claims ingest.

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
