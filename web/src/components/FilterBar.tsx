import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { fetchGeographyIndex } from '../lib/data'
import type { CountyIndexEntry, GeographyIndex } from '../types'
import { BANDS, CLASS_GROUPS, LENSES } from '../types'
import { BAND_LABELS } from '../lib/bands'
import { useFilters } from '../context/useFilters'

// One shared class string, not five near-identical ones -- a real design
// system means every <select> in this bar looks and behaves identically,
// not "identically by coincidence" from copy-pasting.
const SELECT_CLASS =
  'rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800'

export function FilterBar() {
  const { filters, setFilters } = useFilters()
  const [geo, setGeo] = useState<GeographyIndex | null>(null)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { pathname } = useLocation()

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
  const activeFilterCount = [
    filters.countyFips, filters.muniFipsMun, filters.classGroups.length, filters.bands.length,
    filters.minOverlapPct, filters.minAssessedValue,
  ].filter(Boolean).length
  // Band, min overlap %, and min assessed value only ever reach MapCanvas's
  // parcel filter expression -- every other view ignores them, so changing
  // one anywhere but Search & Map silently does nothing. Surface that
  // instead of leaving it to be discovered by a confused click.
  const mapOnlyFiltersInUse =
    pathname !== '/' && (filters.bands.length > 0 || filters.minOverlapPct > 0 || filters.minAssessedValue > 0)

  return (
    <div className="border-t border-zinc-200 bg-zinc-50 px-4 py-2 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mx-auto max-w-7xl">
        <button
          type="button"
          className="mb-2 flex w-full items-center justify-between text-sm font-medium sm:hidden"
          onClick={() => setMobileOpen((o) => !o)}
          aria-expanded={mobileOpen}
          aria-controls="filter-controls"
        >
          <span>Filters{activeFilterCount > 0 ? ` (${activeFilterCount})` : ''}</span>
          <span aria-hidden="true">{mobileOpen ? '▲' : '▼'}</span>
        </button>
        <div
          id="filter-controls"
          className={`${mobileOpen ? 'flex' : 'hidden'} flex-wrap items-end gap-3 text-sm sm:flex`}
        >
        <Field label="County" id="county-filter">
          <select
            id="county-filter"
            className={SELECT_CLASS}
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
            className={SELECT_CLASS}
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
            className={SELECT_CLASS}
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
            className={SELECT_CLASS}
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
            className={SELECT_CLASS}
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
            className="w-32 accent-brand-700"
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
            className="w-28 rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 dark:border-zinc-700 dark:bg-zinc-800"
          />
        </Field>

        {(filters.countyFips || filters.muniFipsMun || filters.classGroups.length || filters.bands.length ||
          filters.minOverlapPct || filters.minAssessedValue) && (
          <button
            type="button"
            className="rounded px-2 py-1 text-brand-700 underline hover:text-brand-900 dark:text-brand-400"
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
        {mapOnlyFiltersInUse && (
          <p className="mt-1.5 text-xs text-amber-700 dark:text-amber-500">
            Band, min overlap, and min assessed value only filter the Search &amp; Map view — they
            don't affect this page.
          </p>
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
