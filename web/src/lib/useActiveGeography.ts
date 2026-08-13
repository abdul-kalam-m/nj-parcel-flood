import { useEffect, useState } from 'react'
import { useFilters } from '../context/useFilters'
import { fetchCountySummary, fetchMuniSummary, fetchStateSummary } from './data'
import type { GeographySummary } from '../types'

export interface ActiveGeography {
  level: 'state' | 'county' | 'muni'
  label: string
  summary: GeographySummary | null
  loading: boolean
}

// §7.2 views 2-4 all key off "the active geography" (state, or the
// county/muni currently selected by the global filters) -- one hook, not
// duplicated per view.
export function useActiveGeography(): ActiveGeography {
  const { filters } = useFilters()
  const [summary, setSummary] = useState<GeographySummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const load = filters.muniFipsMun
      ? fetchMuniSummary(filters.muniFipsMun)
      : filters.countyFips
        ? fetchCountySummary(filters.countyFips)
        : fetchStateSummary()
    load.then((s) => {
      if (!cancelled) {
        setSummary(s)
        setLoading(false)
      }
    })
    return () => {
      cancelled = true
    }
  }, [filters.countyFips, filters.muniFipsMun])

  const level = filters.muniFipsMun ? 'muni' : filters.countyFips ? 'county' : 'state'
  const label = summary?.mun_name ?? summary?.county_name ?? 'New Jersey (statewide)'
  return { level, label, summary, loading }
}
