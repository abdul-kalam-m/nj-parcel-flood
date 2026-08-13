import { useEffect, useState } from 'react'
import { useFilters } from '../context/useFilters'
import { fetchGeographyIndex, fetchMuniSummary, fetchRankedMunicipalities } from '../lib/data'
import type { CountyIndexEntry, GeographyIndex, RankedMuniEntry } from '../types'
import { downloadCsv } from '../lib/csv'
import { bandForPct, BAND_COLORS } from '../lib/bands'

type SortKey = 'pct_at_risk' | 'value_at_risk'

interface Row {
  mun_code: string
  name: string
  fips_mun: string
  pct_at_risk: number
  value_at_risk: number
  parcel_count: number
}

export function RankedMunicipalitiesView() {
  const { filters } = useFilters()
  const [geo, setGeo] = useState<GeographyIndex | null>(null)
  const [ranked, setRanked] = useState<RankedMuniEntry[] | null>(null)
  const [rows, setRows] = useState<Row[] | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('pct_at_risk')

  useEffect(() => {
    fetchGeographyIndex().then(setGeo)
    fetchRankedMunicipalities().then(setRanked)
  }, [])

  const county: CountyIndexEntry | undefined = geo?.counties.find((c) => c.fips === filters.countyFips)
  const countyRanked = ranked?.find((r) => r.county === county?.name.toUpperCase())

  useEffect(() => {
    if (!county || !countyRanked) {
      setRows(null)
      return
    }
    let cancelled = false
    Promise.all(
      county.munis.map(async (m) => {
        const s = await fetchMuniSummary(m.fips_mun)
        const cell = s[filters.lens]?.ALL
        return {
          mun_code: m.mun_code, name: m.name, fips_mun: m.fips_mun,
          pct_at_risk: cell?.pct_at_risk ?? 0,
          value_at_risk: cell?.value_at_risk_presence ?? 0,
          parcel_count: cell?.parcel_count ?? 0,
        }
      }),
    ).then((r) => {
      if (!cancelled) setRows(r)
    })
    return () => {
      cancelled = true
    }
  }, [county, countyRanked, filters.lens])

  if (!filters.countyFips) {
    return (
      <section>
        <h2 className="mb-2 text-2xl font-bold tracking-tight">Ranked municipalities</h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          Select a county in the filter bar above to see its municipalities ranked by % at risk and
          value at risk.
        </p>
      </section>
    )
  }
  if (!rows) return <p className="text-zinc-500">Loading rankings…</p>

  const sorted = [...rows].sort((a, b) => b[sortKey] - a[sortKey])
  const fmtUsd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-2xl font-bold tracking-tight">
          Ranked municipalities — {county?.name} <span className="font-medium text-zinc-500">({filters.lens} risk)</span>
        </h2>
        <div className="flex items-center gap-2">
          <label className="text-sm">
            Sort by{' '}
            <select
              className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 dark:border-zinc-700 dark:bg-zinc-800"
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
            >
              <option value="pct_at_risk">% at risk</option>
              <option value="value_at_risk">Value at risk</option>
            </select>
          </label>
          <button
            type="button"
            className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            onClick={() =>
              downloadCsv(
                `ranked-munis-${county?.name}.csv`,
                sorted.map((r, i) => ({
                  rank: i + 1, municipality: r.name, parcel_count: r.parcel_count,
                  pct_at_risk: r.pct_at_risk, value_at_risk: r.value_at_risk,
                })),
              )
            }
          >
            Export CSV
          </button>
        </div>
      </div>
      <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-zinc-300 bg-zinc-50 text-left font-semibold dark:border-zinc-700 dark:bg-zinc-900">
              <th scope="col" className="py-2 pl-4 pr-4">Rank</th>
              <th scope="col" className="py-2 pr-4">Municipality</th>
              <th scope="col" className="py-2 pr-4 text-right">Parcels</th>
              <th scope="col" className="py-2 pr-4 text-right">% at risk</th>
              <th scope="col" className="py-2 pr-4 text-right">Value at risk</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => (
              <tr
                key={r.fips_mun}
                className="border-b border-zinc-100 odd:bg-zinc-50/70 hover:bg-brand-50 last:border-b-0 dark:border-zinc-800 dark:odd:bg-zinc-900/40 dark:hover:bg-zinc-800"
              >
                <td className="py-1.5 pl-4 pr-4 tabular-nums text-zinc-500">{i + 1}</td>
                <td className="py-1.5 pr-4 font-medium">{r.name}</td>
                <td className="py-1.5 pr-4 text-right tabular-nums">{r.parcel_count.toLocaleString()}</td>
                <td className="py-1.5 pr-4 text-right tabular-nums">
                  {/* border, not just a fill: "none" band's color (#f7f7f7)
                      would otherwise be near-invisible against a white/
                      zebra-striped row. */}
                  <span
                    className="mr-1.5 inline-block h-2 w-2 rounded-full border border-black/15 align-middle"
                    style={{ background: BAND_COLORS[bandForPct(r.pct_at_risk)] }}
                    aria-hidden="true"
                  />
                  {r.pct_at_risk.toFixed(1)}%
                </td>
                <td className="py-1.5 pr-4 text-right tabular-nums">{fmtUsd.format(r.value_at_risk)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
