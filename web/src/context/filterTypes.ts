import { createContext } from 'react'
import type { Band, ClassGroup, Lens } from '../types'

// §7.2: "Filters (global, consistent everywhere): county, muni, class group,
// band, current|future lens, min overlap %, min assessed value."
export interface Filters {
  countyFips: string | null // null = statewide
  muniFipsMun: string | null // null = whole county/state
  classGroups: ClassGroup[] // empty = all
  bands: Band[] // empty = all
  lens: Lens
  minOverlapPct: number
  minAssessedValue: number
}

export const DEFAULT_FILTERS: Filters = {
  countyFips: null,
  muniFipsMun: null,
  classGroups: [],
  bands: [],
  lens: 'either',
  minOverlapPct: 0,
  minAssessedValue: 0,
}

export interface FilterContextValue {
  filters: Filters
  setFilters: (f: Filters | ((prev: Filters) => Filters)) => void
}

export const FilterContext = createContext<FilterContextValue | null>(null)
