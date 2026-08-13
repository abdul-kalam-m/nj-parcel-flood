import { useMemo, useState, type ReactNode } from 'react'
import { DEFAULT_FILTERS, FilterContext, type Filters } from './filterTypes'

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const value = useMemo(() => ({ filters, setFilters }), [filters])
  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>
}
