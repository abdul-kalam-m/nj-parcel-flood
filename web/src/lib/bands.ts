import type { Band } from '../types'

export const BAND_LABELS: Record<Band, string> = {
  none: 'None',
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
}

// Literal hex values -- source of truth for both MapLibre paint expressions
// (which cannot parse CSS custom properties, only literal color values --
// confirmed live: `var(--band-none)` throws "Could not parse color") and
// DOM/Tailwind styling; this is the only place these colors are defined.
export const BAND_COLORS: Record<Band, string> = {
  none: '#f7f7f7',
  low: '#fecc5c',
  moderate: '#fd8d3c',
  high: '#f03b20',
  severe: '#a00000',
}

// WCAG 2.2 AA normal-text contrast (>=4.5:1) against BAND_COLORS, computed
// and verified, not eyeballed -- the first pass used white text on
// "high" (#f03b20) at 3.92:1 and a dark-brown on "moderate" at 4.04:1,
// both just under the threshold; black text clears it comfortably on both.
export const BAND_TEXT_COLORS: Record<Band, string> = {
  none: '#52525b', // 7.22:1
  low: '#713f12', // 5.78:1
  moderate: '#000000', // 9.05:1
  high: '#000000', // 5.35:1
  severe: '#ffffff', // 8.42:1
}

// MapLibre paint-expression form of the same ramp, for parcel fill-color.
export const BAND_MATCH_EXPRESSION = [
  'match', ['get', 'band'],
  'none', BAND_COLORS.none,
  'low', BAND_COLORS.low,
  'moderate', BAND_COLORS.moderate,
  'high', BAND_COLORS.high,
  'severe', BAND_COLORS.severe,
  '#999999',
]
