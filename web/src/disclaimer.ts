// Split out from config.ts (§5.7, verbatim) so it's importable from plain
// Node contexts too -- Playwright test files run under Node, not through
// Vite, so they can't import anything that touches import.meta.env (as
// config.ts's DATA_BASE_URL does) without crashing before a single test runs.
export const DISCLAIMER =
  'Screening tool — not a flood determination. This dashboard combines public parcel, FEMA, NJDEP, and OpenFEMA data with simplified assumptions. Scores are relative screening indicators, not insurance ratings, legal flood-zone determinations, or property valuations. Verify any parcel with official FEMA maps (msc.fema.gov), NJDEP, and municipal records.'
