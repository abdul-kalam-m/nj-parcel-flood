# NJ Parcel Flood Risk Dashboard

**Live demo: [nj-parcel-flood.pages.dev](https://nj-parcel-flood.pages.dev)**

A statewide New Jersey dashboard (~3.4M parcels, 21 counties, 564 municipalities) joining
MOD-IV tax-assessment attributes to parcel geometry, scoring each parcel 0–100 for flood
risk against current (FEMA NFHL) and future (NJDEP climate/SLR) hazard layers plus
tract-level NFIP loss evidence — for parcel search, county/municipality filtering, and
district-at-risk summaries (share of residential/commercial/industrial classes at risk,
by count and assessed value).

> **Screening tool — not a flood determination.** This dashboard combines public parcel,
> FEMA, NJDEP, and OpenFEMA data with simplified assumptions. Scores are relative
> screening indicators, not insurance ratings, legal flood-zone determinations, or
> property valuations. Verify any parcel with official FEMA maps (msc.fema.gov), NJDEP,
> and municipal records.

## Repository layout

- `OPERATING_GUIDE.md` — the canonical build manual. **Read it before doing any work.**
- `PROGRESS.md` — session log (newest entry on top).
- `RECON.md` — Phase 0 data-source recon results.
- `pipeline/` — Python pipeline (recon → parcel core → flood layers → intersections →
  claims → scores → aggregates → tiles → search index → validate).
- `data/` — `raw/`/`processed/` (both gitignored, statewide-scale); `MANIFEST.json`
  records data lineage.
- `artifacts/` — small committed JSON (summaries, meta). Large outputs (tiles, parquet)
  go to Cloudflare R2, not this repo.
- `web/` — Vite + React statewide parcel-search dashboard (from Phase 7).

## Status

Guide-Phase 7 (web app) closed out: search & map (incl. live P8 statewide
address geocoding, a county/muni/parcel detail-level toggle, and hover
tooltips on the map and charts), jurisdiction summary, district exposure,
ranked municipalities, a methodology page (glossary + data sources +
scoring), global filters, CSV export. Municipality choropleth boundary
coverage closed 553/564 → 564/564. `09_validate.py` (§12.1 QA gates)
separately run for real, statewide — **6 of 7 gates PASS**, the one FAIL
being the already-known, owner-approved join-rate limitation carried from
Phase 1 (88.34%, below the guide's ≥97% gate).

An axe/Playwright suite (§12.2 — PIN search → panel, filter cascades,
district chart vs. summary JSON, export + disclaimer, axe scans across all
5 views, plus checks for the toggle's zoom-jump *and* its zoom-floor
locking, and the map tooltip) is implemented and **passing 16/16**, run
repeatedly for stability. Running it for real has repeatedly surfaced and
fixed genuine bugs, not just test-authoring issues — a real accessible-name
defect in the filter bar, a serious axe/WCAG 4.1.2 violation, a duplicated
disclaimer caught via a design-review screenshot, and real CPU-contention
flakiness in the suite itself (fixed by capping worker concurrency, not by
loosening an assertion).

The UI has been through two design passes now, both via
`design:design-critique` against real-browser screenshots (this session's
preview pane can't reliably screenshot or verify MapLibre animations, so
Playwright's real browser does both jobs). The first fixed targeted
usability issues (filters that silently did nothing off the map view, the
detail-level toggle not reading as a map control, mobile filter-bar
length). The second, at the owner's explicit request for a full "UI
overhaul," went further: a real color system (a custom teal `brand` scale
replacing Tailwind's default blue everywhere, contrast-verified and
axe-confirmed), elevation (shadows + rounded corners instead of flat 1px
borders), a real type scale, and the risk-band color ramp reused in stat
cards and tables instead of only appearing on the map.

**Live on Cloudflare Pages + R2** (tiles, search shards, and summaries all
served from R2; the site itself from Pages). Deploying for real — not
just testing against the dev server — caught 2 genuine production-only
bugs: MapLibre's own worker script never actually shipped in the
production build, and fixing that fully required resolving a sibling
internal import too (a first attempt looked complete but the worker still
died silently on load, caught precisely via Playwright's worker-lifecycle
API, not a console error). Both root-caused and confirmed fixed against
the real live URL — actual tile traffic, full search → parcel-panel flow,
all 5 routes.

**The Parcel detail-level toggle's zoom-out floor now genuinely matches
Municipality's (9), not just the button.** Widening it turned out to need
`parcels.pmtiles` itself widened from z13 to z9 (owner: "full scope" once a
cheaper fix — loosening the floor alone — turned out to leave the map
showing the municipality choropleth while the button still said "Parcel").
`MapCanvas.tsx` now explicitly switches which layer is visible per selected
tier, so the existing municipality choropleth isn't regressed for anyone
who never touches the Parcel button. Regenerating the statewide tileset
(3.4M parcels) surfaced two real local-environment blockers, both solved
without touching any security setting: Docker Desktop's WSL2 backend
needed a clean restart, and a Windows Application Control policy was
blocking Python's GDAL bindings natively — worked around by running just
that pipeline step under WSL Ubuntu instead. Verified live on the
production URL: real parcel geometry renders all the way to the shared
floor, the municipality choropleth is unaffected in its own mode. See
`PROGRESS.md` (2026-08-22, "Parcel zoom-out fix, full scope") for full
detail.
