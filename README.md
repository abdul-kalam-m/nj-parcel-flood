# NJ Parcel Flood Risk Dashboard

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
5 views, plus checks for the new toggle and map tooltip) is implemented and
**passing 13/13**. Running it for real has twice surfaced and fixed genuine
bugs, not just test-authoring issues — including a real accessible-name
defect in the filter bar, a serious axe/WCAG 4.1.2 violation in the search
results list, and (caught via a design-review screenshot, not the test
suite) a duplicated disclaimer on the new methodology page. A design pass
after adding the new UI also fixed 3 real usability issues: filters that
silently did nothing outside the map view now say so; the detail-level
toggle is docked onto the map instead of floating next to a caption; the
filter bar collapses on mobile instead of pushing all content below the
fold. See `PROGRESS.md` (2026-08-13) for full detail. R2 upload not yet
done (needs a credentials/infra decision).
