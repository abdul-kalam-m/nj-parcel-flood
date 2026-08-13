// Dev: served locally by vite.config.ts's serveArtifacts plugin from ../artifacts.
// Prod: Cloudflare R2 public bucket (§6.2/§7.1) -- set at build time.
export const DATA_BASE_URL: string =
  (import.meta.env.VITE_DATA_BASE_URL as string | undefined) ?? '/data'

export const DISCLAIMER =
  'Screening tool — not a flood determination. This dashboard combines public parcel, FEMA, NJDEP, and OpenFEMA data with simplified assumptions. Scores are relative screening indicators, not insurance ratings, legal flood-zone determinations, or property valuations. Verify any parcel with official FEMA maps (msc.fema.gov), NJDEP, and municipal records.'
