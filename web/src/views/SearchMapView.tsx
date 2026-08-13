import { useState } from 'react'
import { MapCanvas } from '../components/MapCanvas'
import { ParcelDetailPanel } from '../components/ParcelDetailPanel'
import { MuniSearch } from '../components/MuniSearch'
import { BAND_COLORS, BAND_LABELS } from '../lib/bands'
import { BANDS } from '../types'
import type { ParcelTileProps, SearchRecord } from '../types'

export function SearchMapView() {
  const [selected, setSelected] = useState<ParcelTileProps | null>(null)
  const [flyTo, setFlyTo] = useState<{ lon: number; lat: number; zoom?: number } | null>(null)

  return (
    <section>
      <h2 className="mb-2 text-xl font-semibold sr-only">Search &amp; map</h2>
      <MuniSearch
        onSelect={(r: SearchRecord) => setFlyTo({ lon: r.lon, lat: r.lat })}
      />
      <p className="mb-2 text-xs text-zinc-500">
        County/municipality boundaries are shown below zoom 13, colored by % at risk; individual
        parcels appear at zoom 13+, colored by risk band. Click a parcel for its detail panel.
      </p>
      <div className="flex flex-col gap-4 lg:flex-row">
        <div className="min-w-0 flex-1">
          <MapCanvas onParcelClick={setSelected} flyTo={flyTo} />
          <Legend />
        </div>
        {selected && <ParcelDetailPanel parcel={selected} onClose={() => setSelected(null)} />}
      </div>
    </section>
  )
}

function Legend() {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-3 text-xs" aria-label="Risk band legend">
      <span className="font-medium text-zinc-500">Risk band:</span>
      {BANDS.map((b) => (
        <span key={b} className="flex items-center gap-1">
          <span
            className="inline-block h-3 w-3 rounded-sm border border-black/20"
            style={{ background: BAND_COLORS[b] }}
            aria-hidden="true"
          />
          {BAND_LABELS[b]}
        </span>
      ))}
    </div>
  )
}
