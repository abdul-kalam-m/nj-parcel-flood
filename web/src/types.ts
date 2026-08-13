// Mirrors the real pipeline output schemas exactly (verified against actual
// files under artifacts/, not guessed from the guide's prose description --
// see PROGRESS.md guide-Phase 7 entry).

export const CLASS_GROUPS = [
  'Residential', 'Commercial', 'Industrial', 'Farm/Agricultural',
  'Vacant', 'Public/Institutional/Exempt', 'Other',
] as const
export type ClassGroup = (typeof CLASS_GROUPS)[number]

export const BANDS = ['none', 'low', 'moderate', 'high', 'severe'] as const
export type Band = (typeof BANDS)[number]

export const LENSES = ['current', 'future', 'either'] as const
export type Lens = (typeof LENSES)[number]

export interface ClassGroupStats {
  parcel_count: number
  at_risk_count: number
  pct_at_risk: number
  total_assessed_value: number
  value_at_risk_presence: number
  value_at_risk_overlap: number
  value_exposure_pct: number
}

export type LensSummary = Partial<Record<ClassGroup | 'ALL', ClassGroupStats>>

export interface GeographySummary {
  current: LensSummary
  future: LensSummary
  either: LensSummary
  county_name?: string
  mun_name?: string
}

export interface MuniIndexEntry {
  fips_mun: string
  mun_code: string
  name: string
}
export interface CountyIndexEntry {
  fips: string
  name: string
  munis: MuniIndexEntry[]
}
export interface GeographyIndex {
  counties: CountyIndexEntry[]
}

export interface SearchRecord {
  pin: string
  block: string
  lot: string
  qual: string
  address: string
  lon: number
  lat: number
}

export interface RankedMuniEntry {
  county: string
  rank_by_pct_at_risk: string[] // mun_code, highest-risk first
  rank_by_value_at_risk: string[]
}

// parcels.pmtiles feature properties (pipeline/07_tiles.py's attrs dict).
// Rich enough for the full detail panel straight off a map click -- no
// second parquet fetch needed for the base experience (see guide-Phase 7
// PROGRESS.md entry on why the first, minimal-attrs version wasn't enough).
export interface ParcelTileProps {
  pin: string
  band: Band
  score: number
  class_group: ClassGroup
  prop_class: string
  cur: boolean
  fut: boolean | null // null when fut_cov is false -- "n/a", never "no risk"
  fut_cov: boolean
  sfha_pct: number
  mod_risk_pct: number
  fut_pct: number | null
  c_cur: number
  c_fut: number
  c_loss: number
  situs_address: string
  block: string
  lot: string
  qual: string
  net_value: number | null
  county: string
  mun_name: string
}

// boundaries.pmtiles feature properties (county or muni layer)
export interface BoundaryTileProps {
  fips: string
  fips_mun?: string
  county_name: string
  mun_name?: string
  current_pct_at_risk?: number
  current_value_exposure_pct?: number
  future_pct_at_risk?: number
  future_value_exposure_pct?: number
  either_pct_at_risk?: number
  either_value_exposure_pct?: number
}
