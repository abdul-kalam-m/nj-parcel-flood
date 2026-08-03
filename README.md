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

Phase 0 (bootstrap + recon) in progress. See `PROGRESS.md`.
