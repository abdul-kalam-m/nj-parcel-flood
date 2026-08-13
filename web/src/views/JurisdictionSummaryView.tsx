import { useActiveGeography } from '../lib/useActiveGeography'
import { useFilters } from '../context/useFilters'
import { downloadCsv } from '../lib/csv'
import { bandForPct, BAND_COLORS } from '../lib/bands'
import type { ClassGroup } from '../types'

const fmtInt = new Intl.NumberFormat('en-US')
const fmtUsd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

export function JurisdictionSummaryView() {
  const { label, summary, loading } = useActiveGeography()
  const { filters } = useFilters()

  if (loading) return <p className="text-zinc-500">Loading summary…</p>
  if (!summary) return <p className="text-red-700">Summary unavailable for this geography.</p>

  const selectedClass: ClassGroup | undefined = filters.classGroups[0]
  const classKey: ClassGroup | 'ALL' = selectedClass ?? 'ALL'
  const cell = summary[filters.lens]?.[classKey] ?? summary[filters.lens]?.ALL
  if (!cell) return <p className="text-zinc-500">No data for this selection.</p>

  // Only the two %-based cards get a severity accent (bandForPct, §ux
  // decision in lib/bands.ts) -- raw counts/dollars don't have a "how bad
  // is this" reading the way a percentage does.
  const cards = [
    { title: 'Total parcels', value: fmtInt.format(cell.parcel_count) },
    { title: 'At-risk parcels', value: fmtInt.format(cell.at_risk_count) },
    { title: '% at risk', value: `${cell.pct_at_risk.toFixed(1)}%`, band: bandForPct(cell.pct_at_risk) },
    { title: 'Value at risk (presence-based)', value: fmtUsd.format(cell.value_at_risk_presence) },
    { title: 'Value at risk (overlap-based)', value: fmtUsd.format(cell.value_at_risk_overlap) },
    { title: 'Value exposure %', value: `${cell.value_exposure_pct.toFixed(1)}%`, band: bandForPct(cell.value_exposure_pct) },
  ]

  return (
    <section>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-2xl font-bold tracking-tight">
          Jurisdiction summary — {label}
          {selectedClass && <span className="font-medium text-zinc-500"> · {selectedClass}</span>}
          <span className="font-medium text-zinc-500"> · {filters.lens} risk</span>
        </h2>
        <button
          type="button"
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
          onClick={() =>
            downloadCsv(
              `jurisdiction-summary-${label.replace(/\s+/g, '_')}.csv`,
              [{ geography: label, class_group: classKey, lens: filters.lens, ...cell }],
            )
          }
        >
          Export CSV
        </button>
      </div>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {cards.map((c) => (
          <div
            key={c.title}
            className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900 dark:shadow-none"
            style={c.band ? { borderLeftWidth: 4, borderLeftColor: BAND_COLORS[c.band] } : undefined}
          >
            <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">{c.title}</dt>
            <dd className="mt-1 text-3xl font-bold tabular-nums">{c.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
