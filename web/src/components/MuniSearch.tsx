import { useEffect, useMemo, useState } from 'react'
import { useFilters } from '../context/useFilters'
import { fetchSearchShard } from '../lib/data'
import type { SearchRecord } from '../types'

// §7.1: search shards are "lazy-loaded per selected muni" -- by design, not
// a statewide free-text index. §7.2: "search bar (... or PIN/block-lot via
// shard)" -- this covers that path; live P8 address geocoding is a
// separate, network-dependent path not wired up here (see PROGRESS.md).
export function MuniSearch({ onSelect }: { onSelect: (r: SearchRecord) => void }) {
  const { filters } = useFilters()
  const [records, setRecords] = useState<SearchRecord[] | null>(null)
  const [query, setQuery] = useState('')

  useEffect(() => {
    setRecords(null)
    setQuery('')
    if (!filters.countyFips || !filters.muniFipsMun) return
    const mun2 = filters.muniFipsMun.slice(-2)
    fetchSearchShard(filters.countyFips, mun2).then(setRecords)
  }, [filters.countyFips, filters.muniFipsMun])

  const results = useMemo(() => {
    if (!records || query.trim().length < 2) return []
    const q = query.trim().toLowerCase()
    return records
      .filter(
        (r) =>
          r.pin.toLowerCase().includes(q) ||
          r.address.toLowerCase().includes(q) ||
          `${r.block}/${r.lot}`.includes(q),
      )
      .slice(0, 15)
  }, [records, query])

  if (!filters.countyFips || !filters.muniFipsMun) {
    return (
      <p className="mb-3 text-sm text-zinc-500">
        Select a county and municipality above to search by address, PIN, or block/lot.
      </p>
    )
  }

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
        placeholder={records ? `Search ${records.length} parcels…` : 'Loading parcels…'}
        disabled={!records}
        className="w-full max-w-md rounded border border-zinc-300 px-3 py-1.5 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800"
        role="combobox"
        aria-expanded={results.length > 0}
        aria-controls="search-results"
      />
      {results.length > 0 && (
        <ul
          id="search-results"
          role="listbox"
          aria-label="Search results"
          className="absolute z-10 mt-1 max-h-64 w-full max-w-md overflow-y-auto rounded border border-zinc-300 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-800"
        >
          {results.map((r) => (
            <li key={r.pin} role="option" aria-selected={false}>
              <button
                type="button"
                className="block w-full px-3 py-1.5 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-700"
                onClick={() => {
                  onSelect(r)
                  setQuery('')
                }}
              >
                <span className="font-medium">{r.address || `Block ${r.block} Lot ${r.lot}`}</span>
                <span className="ml-2 text-zinc-400">{r.pin}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
