import type { ParcelTileProps } from '../types'
import { BAND_COLORS, BAND_LABELS, BAND_TEXT_COLORS } from '../lib/bands'

const fmtUsd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const pct = (frac: number) => `${(frac * 100).toFixed(1)}%`

// §7.2: "parcel detail panel (attrs, flags, score + drivers §5.3)". §5.3:
// "The parcel panel must show all three component values and the inputs
// behind them (the 'drivers' requirement)."
export function ParcelDetailPanel({ parcel, onClose }: { parcel: ParcelTileProps; onClose: () => void }) {
  return (
    <aside
      aria-label="Parcel detail"
      className="w-full max-w-sm shrink-0 overflow-y-auto rounded-lg border border-zinc-200 p-4 shadow-sm dark:border-zinc-800 dark:shadow-none"
    >
      <div className="mb-2 flex items-start justify-between">
        <h3 className="text-sm font-semibold text-zinc-500">Parcel {parcel.pin}</h3>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close parcel detail"
          className="rounded-full p-1 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
        >
          ✕
        </button>
      </div>

      <p className="mb-1 text-lg font-medium">{parcel.situs_address || '(no address on record)'}</p>
      <p className="mb-3 text-sm text-zinc-500">
        {parcel.mun_name || parcel.county}, {parcel.county} County · Block {parcel.block}, Lot {parcel.lot}
        {parcel.qual.trim() ? `, Qual ${parcel.qual}` : ''}
      </p>

      <div
        className="mb-3 flex items-center justify-between rounded-lg p-3"
        style={{ background: BAND_COLORS[parcel.band], color: BAND_TEXT_COLORS[parcel.band] }}
      >
        <span className="text-sm font-medium">Risk band: {BAND_LABELS[parcel.band]}</span>
        <span className="text-2xl font-bold tabular-nums">{parcel.score}</span>
      </div>

      <dl className="mb-3 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
        <dt className="text-zinc-500">Class</dt>
        <dd>{parcel.class_group} <span className="text-zinc-400">({parcel.prop_class || '—'})</span></dd>
        <dt className="text-zinc-500">Assessed value</dt>
        <dd>{parcel.net_value != null ? fmtUsd.format(parcel.net_value) : 'not on record'}</dd>
        <dt className="text-zinc-500">Current risk flag</dt>
        <dd>{parcel.cur ? 'Yes' : 'No'}</dd>
        <dt className="text-zinc-500">Future risk flag</dt>
        <dd>{parcel.fut_cov ? (parcel.fut ? 'Yes' : 'No') : 'n/a — no future data here'}</dd>
      </dl>

      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
        Score drivers (§5.3)
      </h4>
      <table className="w-full text-sm">
        <thead className="sr-only">
          <tr><th>Component</th><th>Weight</th><th>Value</th><th>Input</th></tr>
        </thead>
        <tbody>
          <tr className="border-b border-zinc-100 dark:border-zinc-800">
            <td className="py-1">C_cur (current)</td>
            <td className="py-1 text-zinc-400">×0.45</td>
            <td className="py-1 text-right tabular-nums">{pct(parcel.c_cur)}</td>
          </tr>
          <tr className="border-b border-zinc-100 pl-2 text-xs text-zinc-500 dark:border-zinc-800">
            <td colSpan={3} className="pb-1 pl-2">
              SFHA overlap {pct(parcel.sfha_pct)} · moderate (shaded X) overlap {pct(parcel.mod_risk_pct)}
            </td>
          </tr>
          <tr className="border-b border-zinc-100 dark:border-zinc-800">
            <td className="py-1">C_fut (future)</td>
            <td className="py-1 text-zinc-400">×0.30</td>
            <td className="py-1 text-right tabular-nums">{pct(parcel.c_fut)}</td>
          </tr>
          <tr className="border-b border-zinc-100 pl-2 text-xs text-zinc-500 dark:border-zinc-800">
            <td colSpan={3} className="pb-1 pl-2">
              {parcel.fut_cov
                ? `Future-layer overlap ${pct(parcel.fut_pct ?? 0)}`
                : 'No future-layer data here — estimated from current risk × 0.5'}
            </td>
          </tr>
          <tr>
            <td className="py-1">C_loss (tract history)</td>
            <td className="py-1 text-zinc-400">×0.25</td>
            <td className="py-1 text-right tabular-nums">{pct(parcel.c_loss)}</td>
          </tr>
        </tbody>
      </table>
    </aside>
  )
}
