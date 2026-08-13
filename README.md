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
address geocoding), jurisdiction summary, district exposure, ranked
municipalities, global filters, CSV export. Municipality choropleth boundary
coverage closed 553/564 → 564/564. `09_validate.py` (§12.1 QA gates)
separately run for real, statewide — **6 of 7 gates PASS**, the one FAIL
being the already-known, owner-approved join-rate limitation carried from
Phase 1 (88.34%, below the guide's ≥97% gate).

An axe/Playwright suite (§12.2 — PIN search → panel, filter cascades,
district chart vs. summary JSON, export + disclaimer, axe scans across all
4 views) is implemented and **passing 10/10**. Running it for real surfaced
and fixed 3 genuine bugs, not just test-authoring issues — most notably a
real accessible-name defect in the filter bar (implicit label-wrapping was
folding a control's own option text into its computed name) and a serious
axe/WCAG 4.1.2 violation in the search results list (an interactive button
nested inside an ARIA `option` element). Running in a real browser, the
suite also independently confirms the map's fly-to → parcel-panel chain
end-to-end, closing a gap this session's preview-pane tooling had left
unverified. See `PROGRESS.md` (2026-08-13) for full detail. R2 upload not
yet done (needs a credentials/infra decision).
