import { useEffect, useMemo, useState } from 'react'
import { useFilters } from '../context/useFilters'
import { fetchSearchShard } from '../lib/data'
import { geocodeAddress, type GeocodeCandidate } from '../lib/geocode'
import type { SearchRecord } from '../types'

const GEOCODE_DEBOUNCE_MS = 400
const GEOCODE_MIN_QUERY_LEN = 5 // shorter queries are rarely a real address attempt

// §7.2: "search bar (address via P8 geocode -> point -> parcel hit; or
// PIN/block-lot via shard)" -- one input, two independent sources: the local
// shard (instant, only once a muni is selected -- §7.1's "lazy-loaded per
// selected muni" design) and live P8 geocoding (statewide, always available,
// network-bound, debounced so it doesn't fire on every keystroke).
export function MuniSearch({ onSelect }: { onSelect: (r: SearchRecord) => void }) {
  const { filters } = useFilters()
  const [records, setRecords] = useState<SearchRecord[] | null>(null)
  const [query, setQuery] = useState('')
  const [geoResults, setGeoResults] = useState<GeocodeCandidate[]>([])
  const [geoLoading, setGeoLoading] = useState(false)

  useEffect(() => {
    setRecords(null)
    if (!filters.countyFips || !filters.muniFipsMun) return
    const mun2 = filters.muniFipsMun.slice(-2)
    fetchSearchShard(filters.countyFips, mun2).then(setRecords)
  }, [filters.countyFips, filters.muniFipsMun])

  const localResults = useMemo(() => {
    if (!records || query.trim().length < 2) return []
    const q = query.trim().toLowerCase()
    return records
      .filter(
        (r) =>
          r.pin.toLowerCase().includes(q) ||
          r.address.toLowerCase().includes(q) ||
          `${r.block}/${r.lot}`.includes(q),
      )
      .slice(0, 10)
  }, [records, query])

  useEffect(() => {
    if (query.trim().length < GEOCODE_MIN_QUERY_LEN) {
      setGeoResults([])
      setGeoLoading(false)
      return
    }
    let cancelled = false
    const controller = new AbortController()
    setGeoLoading(true)
    const timer = setTimeout(() => {
      geocodeAddress(query.trim(), controller.signal).then((results) => {
        if (!cancelled) {
          setGeoResults(results)
          setGeoLoading(false)
        }
      })
    }, GEOCODE_DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
      controller.abort()
    }
  }, [query])

  const clearSearch = () => {
    setQuery('')
    setGeoResults([])
  }

  const hasResults = localResults.length > 0 || geoResults.length > 0

  return (
    <div className="relative mb-3">
      <label htmlFor="parcel-search" className="mb-1 block text-sm font-medium">
        Search address, PIN, or block/lot
      </label>
      <input
        id="parcel-search"
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={
          filters.muniFipsMun
            ? records
              ? `Search ${records.length} parcels, or any NJ address…`
              : 'Loading parcels…'
            : 'Search any NJ address (pick a county + municipality too for PIN/block-lot search)'
        }
        className="w-full max-w-md rounded border border-zinc-300 px-3 py-1.5 dark:border-zinc-700 dark:bg-zinc-800"
        role="combobox"
        aria-expanded={hasResults}
        aria-controls="search-results"
      />
      {geoLoading && (
        <p className="mt-1 text-xs text-zinc-500" role="status">
          Searching statewide address index…
        </p>
      )}
      {hasResults && (
        <ul
          id="search-results"
          role="listbox"
          aria-label="Search results"
          className="absolute z-10 mt-1 max-h-72 w-full max-w-md overflow-y-auto rounded border border-zinc-300 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-800"
        >
          {localResults.map((r) => (
            <li key={r.pin} role="option" aria-selected={false}>
              <button
                type="button"
                className="block w-full px-3 py-1.5 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-700"
                onClick={() => {
                  onSelect(r)
                  clearSearch()
                }}
              >
                <span className="font-medium">{r.address || `Block ${r.block} Lot ${r.lot}`}</span>
                <span className="ml-2 text-zinc-400">{r.pin}</span>
              </button>
            </li>
          ))}
          {geoResults.map((g) => (
            <li key={g.address} role="option" aria-selected={false}>
              <button
                type="button"
                className="block w-full px-3 py-1.5 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-700"
                onClick={() => {
                  onSelect({ pin: '', block: '', lot: '', qual: '', address: g.address, lon: g.lon, lat: g.lat })
                  clearSearch()
                }}
              >
                <span aria-hidden="true">📍 </span>
                <span className="font-medium">{g.address}</span>
                <span className="ml-2 text-zinc-400">statewide geocode</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
