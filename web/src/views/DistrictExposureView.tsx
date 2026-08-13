import { useState } from 'react'
import { useActiveGeography } from '../lib/useActiveGeography'
import { useFilters } from '../context/useFilters'
import { CLASS_GROUPS } from '../types'
import { downloadCsv } from '../lib/csv'

type Metric = 'count' | 'value'

export function DistrictExposureView() {
  const { label, summary, loading } = useActiveGeography()
  const { filters } = useFilters()
  const [metric, setMetric] = useState<Metric>('count')

  if (loading) return <p className="text-zinc-500">Loading exposure data…</p>
  if (!summary) return <p className="text-red-700">Data unavailable for this geography.</p>

  const rows = CLASS_GROUPS.map((cg) => {
    const cur = summary.current[cg]
    const fut = summary.future[cg]
    return {
      classGroup: cg,
      current: cur ? (metric === 'count' ? cur.pct_at_risk : cur.value_exposure_pct) : 0,
      future: fut ? (metric === 'count' ? fut.pct_at_risk : fut.value_exposure_pct) : 0,
      currentCell: cur,
      futureCell: fut,
    }
  }).filter((r) => !filters.classGroups.length || filters.classGroups.includes(r.classGroup))

  const maxVal = Math.max(1, ...rows.flatMap((r) => [r.current, r.future]))
  const chartH = 220
  const barGroupW = 64
  const barW = 20

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">District exposure — {label}</h2>
        <div className="flex items-center gap-3">
          <div role="group" aria-label="Metric" className="flex overflow-hidden rounded border border-zinc-300 dark:border-zinc-700">
            {(['count', 'value'] as Metric[]).map((m) => (
              <button
                key={m}
                type="button"
                aria-pressed={metric === m}
                className={`px-3 py-1 text-sm ${metric === m ? 'bg-blue-700 text-white' : 'bg-white dark:bg-zinc-800'}`}
                onClick={() => setMetric(m)}
              >
                {m === 'count' ? '% of parcels' : '% of value'}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            onClick={() =>
              downloadCsv(
                `district-exposure-${label.replace(/\s+/g, '_')}.csv`,
                rows.map((r) => ({
                  class_group: r.classGroup,
                  current_pct_at_risk: r.currentCell?.pct_at_risk ?? 0,
                  current_value_exposure_pct: r.currentCell?.value_exposure_pct ?? 0,
                  future_pct_at_risk: r.futureCell?.pct_at_risk ?? 0,
                  future_value_exposure_pct: r.futureCell?.value_exposure_pct ?? 0,
                })),
              )
            }
          >
            Export CSV
          </button>
        </div>
      </div>

      <p className="mb-2 text-xs text-zinc-500">
        Current and future bars are shown side by side, not summed — a parcel can carry both, so a
        stacked total would double-count it.
      </p>

      <svg
        role="img"
        aria-label={`Bar chart of ${metric === 'count' ? 'percent of parcels' : 'percent of value'} at risk by class group, current versus future`}
        viewBox={`0 0 ${rows.length * barGroupW + 40} ${chartH + 60}`}
        className="w-full max-w-3xl"
      >
        <line x1={40} y1={chartH} x2={rows.length * barGroupW + 30} y2={chartH} stroke="currentColor" opacity={0.3} />
        {rows.map((r, i) => {
          const x = 40 + i * barGroupW
          const curH = (r.current / maxVal) * chartH
          const futH = (r.future / maxVal) * chartH
          return (
            <g key={r.classGroup}>
              <rect x={x} y={chartH - curH} width={barW} height={curH} fill="#1d4ed8">
                <title>{`${r.classGroup} · current: ${r.current.toFixed(1)}%`}</title>
              </rect>
              <rect x={x + barW + 4} y={chartH - futH} width={barW} height={futH} fill="#f97316">
                <title>{`${r.classGroup} · future: ${r.future.toFixed(1)}%`}</title>
              </rect>
              <text x={x + barW} y={chartH + 14} fontSize={9} textAnchor="middle" fill="currentColor">
                {r.classGroup.length > 10 ? r.classGroup.slice(0, 9) + '…' : r.classGroup}
              </text>
            </g>
          )
        })}
        <g transform={`translate(40, ${chartH + 34})`} fontSize={10} fill="currentColor">
          <rect width={10} height={10} fill="#1d4ed8" />
          <text x={14} y={9}>Current</text>
          <rect x={80} width={10} height={10} fill="#f97316" />
          <text x={94} y={9}>Future</text>
        </g>
      </svg>

      <table className="mt-6 w-full border-collapse text-sm">
        <caption className="mb-2 text-left text-xs text-zinc-500">
          District exposure by class group — {metric === 'count' ? '% of parcels' : '% of value'} at risk
        </caption>
        <thead>
          <tr className="border-b border-zinc-300 text-left dark:border-zinc-700">
            <th scope="col" className="py-1 pr-4">Class group</th>
            <th scope="col" className="py-1 pr-4 text-right">Current %</th>
            <th scope="col" className="py-1 pr-4 text-right">Future %</th>
            <th scope="col" className="py-1 pr-4 text-right">Parcels</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.classGroup} className="border-b border-zinc-100 dark:border-zinc-800">
              <td className="py-1 pr-4">{r.classGroup}</td>
              <td className="py-1 pr-4 text-right tabular-nums">{r.current.toFixed(1)}%</td>
              <td className="py-1 pr-4 text-right tabular-nums">{r.future.toFixed(1)}%</td>
              <td className="py-1 pr-4 text-right tabular-nums">{r.currentCell?.parcel_count ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
