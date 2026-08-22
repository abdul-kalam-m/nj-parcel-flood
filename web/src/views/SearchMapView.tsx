import { useState } from 'react'
import { MapCanvas } from '../components/MapCanvas'
import { ParcelDetailPanel } from '../components/ParcelDetailPanel'
import { MuniSearch } from '../components/MuniSearch'
import { BAND_COLORS, BAND_LABELS } from '../lib/bands'
import { BANDS } from '../types'
import type { ParcelTileProps, SearchRecord } from '../types'

// Mirrors the layer minzoom/maxzoom thresholds in MapCanvas.tsx: counties
// render up to zoom 13, munis from 9-13 (on top of counties), parcels from
// 13 up. The toggle jumps to a representative zoom inside each tier rather
// than re-centering -- there's no per-geography centroid in the current
// pipeline output to fly to, so this controls zoom only, from wherever the
// map already is.
type MapLevel = 'county' | 'municipality' | 'parcel'
const LEVEL_ZOOM: Record<MapLevel, number> = { county: 7.2, municipality: 10.5, parcel: 14 }
const LEVEL_LABELS: Record<MapLevel, string> = { county: 'County', municipality: 'Municipality', parcel: 'Parcel' }
// Each level's own lower zoom boundary. Picking a level sets this as the
// map's floor so scrolling *out* can't cross back into a lower tier;
// scrolling *in* is never restricted. County has no lower tier to guard
// against, so 0 (no floor) is correct there. Parcel's floor is 13, not
// shared with Municipality's 9 -- tried loosening it to 9 first, but
// parcels.pmtiles is only ever generated with tile data from z13 up
// (pipeline/07_tiles.py: `tippecanoe -Z13 -z16`), so below 13 there is no
// parcel geometry in the file at all, full stop -- not a rendering
// setting, a fact about what's actually in the tileset. A wider floor let
// the toggle stay pinned on "Parcel" while the map itself fell back to
// showing the municipality choropleth underneath, which read as broken
// (button says Parcel, map shows munis) more than it read as useful.
// Owner chose consistency over more zoom-out room: selecting Parcel now
// always means real parcel geometry is what's on screen.
const LEVEL_MIN_ZOOM: Record<MapLevel, number> = { county: 0, municipality: 9, parcel: 13 }

export function SearchMapView() {
  const [selected, setSelected] = useState<ParcelTileProps | null>(null)
  const [flyTo, setFlyTo] = useState<{ lon: number; lat: number; zoom?: number } | null>(null)
  const [zoomTo, setZoomTo] = useState<{ zoom: number; minZoom: number } | null>(null)
  // Sticky: only changes on an explicit click, matching the initial zoom
  // (7.2, county range) at mount. Deliberately does *not* track live zoom
  // (it used to, via MapCanvas's onZoomChange) -- owner feedback: after
  // clicking Parcel, scrolling out into muni-range territory flipped the
  // toggle to "Municipality", which read as the map undoing the user's own
  // choice rather than just showing what's currently in view.
  const [selectedLevel, setSelectedLevel] = useState<MapLevel>('county')

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
          {/* Docked onto the map itself, like MapLibre's own zoom control --
              reads as a map control, not a caption sitting next to one. */}
          <div className="relative">
            <MapCanvas onParcelClick={setSelected} flyTo={flyTo} zoomTo={zoomTo} />
            <div className="absolute left-2 top-2 z-10">
              <MapLevelToggle
                level={selectedLevel}
                onSelect={(l) => {
                  setSelectedLevel(l)
                  setZoomTo({ zoom: LEVEL_ZOOM[l], minZoom: LEVEL_MIN_ZOOM[l] })
                }}
              />
            </div>
          </div>
          <Legend />
        </div>
        {selected && <ParcelDetailPanel parcel={selected} onClose={() => setSelected(null)} />}
      </div>
    </section>
  )
}

function MapLevelToggle({ level, onSelect }: { level: MapLevel; onSelect: (l: MapLevel) => void }) {
  return (
    <div className="flex items-center gap-1.5 rounded-lg bg-white/90 px-1.5 py-1 text-xs shadow-md backdrop-blur-sm dark:bg-zinc-900/90">
      <span className="pl-0.5 font-medium text-zinc-500 dark:text-zinc-400">Zoom to:</span>
      <div
        role="group"
        aria-label="Map detail level"
        className="flex overflow-hidden rounded-md border border-zinc-300 dark:border-zinc-700"
      >
        {(['county', 'municipality', 'parcel'] as MapLevel[]).map((l) => (
          <button
            key={l}
            type="button"
            aria-pressed={level === l}
            title={`Jump to ${LEVEL_LABELS[l].toLowerCase()}-level zoom`}
            className={`px-2 py-1 font-medium transition-colors ${
              level === l ? 'bg-brand-700 text-white' : 'bg-white hover:bg-zinc-100 dark:bg-zinc-800 dark:hover:bg-zinc-700'
            }`}
            onClick={() => onSelect(l)}
          >
            {LEVEL_LABELS[l]}
          </button>
        ))}
      </div>
    </div>
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
