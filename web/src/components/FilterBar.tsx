import { useEffect, useState } from 'react'
import { fetchGeographyIndex } from '../lib/data'
import type { CountyIndexEntry, GeographyIndex } from '../types'
import { BANDS, CLASS_GROUPS, LENSES } from '../types'
import { BAND_LABELS } from '../lib/bands'
import { useFilters } from '../context/useFilters'

export function FilterBar() {
  const { filters, setFilters } = useFilters()
  const [geo, setGeo] = useState<GeographyIndex | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchGeographyIndex().then((g) => {
      if (!cancelled) setGeo(g)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const selectedCounty: CountyIndexEntry | undefined = geo?.counties.find(
    (c) => c.fips === filters.countyFips,
  )

  return (
    <div className="border-t border-zinc-200 bg-zinc-50 px-4 py-2 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mx-auto flex max-w-7xl flex-wrap items-end gap-3 text-sm">
        <Field label="County" id="county-filter">
          <select
            id="county-filter"
            className="rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-800"
            value={filters.countyFips ?? ''}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                countyFips: e.target.value || null,
                muniFipsMun: null, // changing county clears the muni selection
              }))
            }
          >
            <option value="">All counties (statewide)</option>
            {geo?.counties.map((c) => (
              <option key={c.fips} value={c.fips}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Municipality" id="muni-filter">
          <select
            id="muni-filter"
            className="rounded border border-zinc-300 bg-white px-2 py-1 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800"
            value={filters.muniFipsMun ?? ''}
            disabled={!selectedCounty}
            onChange={(e) => setFilters((f) => ({ ...f, muniFipsMun: e.target.value || null }))}
          >
            <option value="">{selectedCounty ? 'All municipalities' : 'Select a county first'}</option>
            {selectedCounty?.munis.map((m) => (
              <option key={m.fips_mun} value={m.fips_mun}>
                {m.name}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Lens" id="lens-filter">
          <select
            id="lens-filter"
            className="rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-800"
            value={filters.lens}
            onChange={(e) => setFilters((f) => ({ ...f, lens: e.target.value as typeof f.lens }))}
          >
            {LENSES.map((l) => (
              <option key={l} value={l}>
                {l === 'current' ? 'Current risk' : l === 'future' ? 'Future risk' : 'Either'}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Class group" id="class-group-filter">
          <select
            id="class-group-filter"
            className="rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-800"
            value={filters.classGroups[0] ?? ''}
            onChange={(e) =>
              setFilters((f) => ({ ...f, classGroups: e.target.value ? [e.target.value as typeof f.classGroups[number]] : [] }))
            }
          >
            <option value="">All classes</option>
            {CLASS_GROUPS.map((cg) => (
              <option key={cg} value={cg}>
                {cg}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Band" id="band-filter">
          <select
            id="band-filter"
            className="rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-800"
            value={filters.bands[0] ?? ''}
            onChange={(e) =>
              setFilters((f) => ({ ...f, bands: e.target.value ? [e.target.value as typeof f.bands[number]] : [] }))
            }
          >
            <option value="">All bands</option>
            {BANDS.map((b) => (
              <option key={b} value={b}>
                {BAND_LABELS[b]}
              </option>
            ))}
          </select>
        </Field>

        <Field label={`Min overlap: ${filters.minOverlapPct}%`} id="min-overlap-filter">
          <input
            id="min-overlap-filter"
            type="range"
            min={0}
            max={100}
            step={5}
            value={filters.minOverlapPct}
            onChange={(e) => setFilters((f) => ({ ...f, minOverlapPct: Number(e.target.value) }))}
            className="w-32"
            aria-valuetext={`${filters.minOverlapPct} percent`}
          />
        </Field>

        <Field label="Min assessed value ($)" id="min-assessed-value-filter">
          <input
            id="min-assessed-value-filter"
            type="number"
            min={0}
            step={10000}
            value={filters.minAssessedValue || ''}
            placeholder="0"
            onChange={(e) => setFilters((f) => ({ ...f, minAssessedValue: Number(e.target.value) || 0 }))}
            className="w-28 rounded border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-800"
          />
        </Field>

        {(filters.countyFips || filters.muniFipsMun || filters.classGroups.length || filters.bands.length ||
          filters.minOverlapPct || filters.minAssessedValue) && (
          <button
            type="button"
            className="rounded px-2 py-1 text-blue-700 underline hover:text-blue-900 dark:text-blue-400"
            onClick={() =>
              setFilters((f) => ({
                countyFips: null, muniFipsMun: null, classGroups: [], bands: [],
                lens: f.lens, minOverlapPct: 0, minAssessedValue: 0,
              }))
            }
          >
            Clear filters
          </button>
        )}
      </div>
    </div>
  )
}

// Explicit id/htmlFor association (not implicit label-wrapping): a <label> that
// *wraps* a <select> can end up with the select's own displayed option text
// folded into the accessible name the browser computes for it (e.g. "County"
// becomes "CountyAll counties (statewide)"), which is enough to make
// Playwright's getByLabel('County') ambiguously match the Municipality field
// too, since its placeholder option reads "Select a county first". Explicit
// association keeps each control's accessible name exactly its label text.
function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <label htmlFor={id} className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
        {label}
      </label>
      {children}
    </div>
  )
}
