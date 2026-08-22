import { useEffect, useRef } from 'react'
import {
  MapLibreMap, NavigationControl, Popup, addProtocol, setWorkerUrl,
  type ExpressionSpecification, type MapLayerMouseEvent,
} from 'maplibre-gl'
import { Protocol } from 'pmtiles'
import { DATA_BASE_URL } from '../config'
import { useFilters } from '../context/useFilters'
import { BAND_LABELS, BAND_MATCH_EXPRESSION } from '../lib/bands'
import type { BoundaryTileProps, ParcelTileProps } from '../types'

// Prod only: dev's existing fix for maplibre-gl's worker (optimizeDeps.exclude
// below) already makes its own default `new Worker(new URL(...))` reference
// resolve correctly there, so this isn't needed -- and calling it
// unconditionally would point dev at a file vite.config.ts's build-only
// copy-plugin never emits in dev mode. In prod, that plugin emits
// maplibre-gl-worker.mjs *and* its sibling maplibre-gl-shared.mjs (the
// worker's own internal `import ... from "./maplibre-gl-shared.mjs"`) at
// the site root with unhashed names, so this relative import resolves --
// a plain hashed-asset copy of the worker alone left that import
// unresolved: the browser created the Worker, its module eval threw, and
// it closed within milliseconds with no console error, before ever
// requesting a single tile (confirmed live via Playwright's
// page.on('worker') -- 'created' then 'closed', not caught by the
// pane-limited manual check that shipped the original, incomplete fix).
if (import.meta.env.PROD) {
  setWorkerUrl('/maplibre-gl-worker.mjs')
}

// P9 basemap (§4/§6.2): OpenFreeMap vector tiles, no API key, no Mapbox/Google dependency.
const BASEMAP_STYLE = 'https://tiles.openfreemap.org/styles/liberty'

let protocolRegistered = false
function ensurePmtilesProtocol() {
  if (protocolRegistered) return
  const protocol = new Protocol()
  addProtocol('pmtiles', protocol.tile)
  protocolRegistered = true
}

// Continuous choropleth ramp for county/muni % at risk (0-100), same
// endpoints as the parcel band colors for visual consistency, but
// interpolated since this is a continuous value, not a category.
function choroplethExpr(lens: 'current' | 'future' | 'either'): ExpressionSpecification {
  return [
    'interpolate', ['linear'], ['coalesce', ['get', `${lens}_pct_at_risk`], 0],
    0, '#f7f7f7', 10, '#fecc5c', 25, '#fd8d3c', 45, '#f03b20', 70, '#a00000',
  ]
}

// Owned here, not in SearchMapView.tsx: this component is the one that
// actually needs it for layer-visibility logic below, not just for
// labeling a button.
export type MapLevel = 'county' | 'municipality' | 'parcel'

export interface MapCanvasProps {
  onParcelClick: (props: ParcelTileProps) => void
  flyTo?: { lon: number; lat: number; zoom?: number } | null
  // Detail-level toggle (county/muni/parcel): jumps the current zoom only,
  // keeping the map centered where it already is -- deliberately separate
  // from `flyTo` above, which also re-centers *and* selects whatever parcel
  // ends up at the target point. Conflating the two would pop the parcel
  // panel open every time someone just wants to change zoom tiers.
  // `minZoom` is the chosen tier's own lower boundary -- once set, scrolling
  // out can't cross back past it into a lower tier; scrolling in stays
  // unrestricted.
  zoomTo?: { zoom: number; minZoom: number } | null
  // The toggle's own sticky selection (SearchMapView.tsx), not derived from
  // live zoom. parcels.pmtiles now carries real geometry from z9 up (widened
  // from its original z13, PROGRESS.md 2026-08-13 "Parcel zoom-out fix,
  // full scope"), the same floor Municipality already used -- but 9-13 is
  // also munis-fill's own native range, so both layers are simultaneously
  // *eligible* to render there by zoom alone. Only one should actually show:
  // parcels specifically when Parcel is the selected tier (so scrolling out
  // from an individual parcel keeps showing real parcels, not the
  // municipality choropleth underneath), the existing muni choropleth
  // otherwise (so ordinary browsing through that zoom band -- never having
  // touched the Parcel button -- looks exactly as it always has).
  activeLevel: MapLevel
}

export function MapCanvas({ onParcelClick, flyTo, zoomTo, activeLevel }: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const { filters } = useFilters()
  // Read inside the mount effect's event handlers (registered once, `[]`
  // deps) without making the whole map re-init on every activeLevel change
  // -- same established pattern as the other props this component captures
  // once and reads live via a ref.
  const activeLevelRef = useRef(activeLevel)
  activeLevelRef.current = activeLevel
  // Set by the mount effect once the map exists, called both from there and
  // from the activeLevel-change effect further down.
  const updateTierVisibilityRef = useRef<() => void>(() => {})

  useEffect(() => {
    if (!containerRef.current) return
    ensurePmtilesProtocol()

    const map = new MapLibreMap({
      container: containerRef.current,
      style: BASEMAP_STYLE,
      center: [-74.5, 40.1], // roughly central NJ
      zoom: 7.2,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')

    map.on('load', () => {
      map.addSource('boundaries', { type: 'vector', url: `pmtiles://${DATA_BASE_URL}/tiles/boundaries.pmtiles` })
      map.addSource('parcels', { type: 'vector', url: `pmtiles://${DATA_BASE_URL}/tiles/parcels.pmtiles` })

      map.addLayer({
        id: 'counties-fill', type: 'fill', source: 'boundaries', 'source-layer': 'counties',
        maxzoom: 13,
        paint: { 'fill-color': choroplethExpr('either'), 'fill-opacity': 0.75 },
      })
      map.addLayer({
        id: 'counties-outline', type: 'line', source: 'boundaries', 'source-layer': 'counties',
        maxzoom: 13,
        paint: { 'line-color': '#52525b', 'line-width': 1 },
      })
      map.addLayer({
        id: 'munis-fill', type: 'fill', source: 'boundaries', 'source-layer': 'munis',
        minzoom: 9, maxzoom: 13,
        paint: { 'fill-color': choroplethExpr('either'), 'fill-opacity': 0.75 },
      })
      map.addLayer({
        id: 'munis-outline', type: 'line', source: 'boundaries', 'source-layer': 'munis',
        minzoom: 9, maxzoom: 13,
        paint: { 'line-color': '#71717a', 'line-width': 0.5 },
      })
      map.addLayer({
        id: 'parcels-fill', type: 'fill', source: 'parcels', 'source-layer': 'parcels',
        minzoom: 9,
        paint: { 'fill-color': BAND_MATCH_EXPRESSION as unknown as ExpressionSpecification, 'fill-opacity': 0.8 },
      })
      map.addLayer({
        id: 'parcels-outline', type: 'line', source: 'parcels', 'source-layer': 'parcels',
        minzoom: 9,
        paint: { 'line-color': '#000000', 'line-width': 0.3, 'line-opacity': 0.3 },
      })

      map.on('click', 'parcels-fill', (e: MapLayerMouseEvent) => {
        const f = e.features?.[0]
        if (f) onParcelClick(f.properties as ParcelTileProps)
      })
      map.on('mouseenter', 'parcels-fill', () => {
        map.getCanvas().style.cursor = 'pointer'
      })
      map.on('mouseleave', 'parcels-fill', () => {
        map.getCanvas().style.cursor = ''
      })

      // Hover tooltip across all 3 tiers, one unified handler rather than
      // one per layer. munis-fill and parcels-fill are now both *eligible*
      // to render across the same 9-13 zoom band, but updateTierVisibility()
      // below always keeps exactly one of them set to visibility:none there
      // -- queryRenderedFeatures only returns hits from layers actually
      // being rendered, so querying all three together still can't produce
      // a conflicting pair of hits, same as when the ranges were disjoint.
      const tooltip = new Popup({ closeButton: false, closeOnClick: false, maxWidth: '260px' })
      const fmtPct = (v: number | undefined | null) => (v == null ? 'n/a' : `${v.toFixed(1)}%`)
      map.on('mousemove', (e) => {
        const hits = map.queryRenderedFeatures(e.point, {
          layers: ['munis-fill', 'counties-fill', 'parcels-fill'],
        })
        const f = hits[0]
        if (!f) {
          tooltip.remove()
          return
        }
        let html: string
        if (f.layer.id === 'parcels-fill') {
          const p = f.properties as ParcelTileProps
          html = `<strong>${p.situs_address || `Block ${p.block} Lot ${p.lot}`}</strong><br>
            PIN ${p.pin} &middot; ${BAND_LABELS[p.band]} risk (score ${p.score})`
        } else {
          const b = f.properties as BoundaryTileProps
          const name = f.layer.id === 'munis-fill' ? (b.mun_name ?? b.county_name) : b.county_name
          html = `<strong>${name}</strong><br>
            Current: ${fmtPct(b.current_pct_at_risk)} at risk &middot;
            Future: ${fmtPct(b.future_pct_at_risk)} at risk`
        }
        tooltip.setLngLat(e.lngLat).setHTML(html).addTo(map)
      })
      map.on('mouseout', () => tooltip.remove())

      // munis-fill and parcels-fill are both zoom-eligible across 9-13 now
      // (parcels.pmtiles widened from z13 to z9, PROGRESS.md 2026-08-13) --
      // exactly one of them should actually be visible there: parcels when
      // Parcel is the selected tier (so zooming out from one parcel keeps
      // showing real parcels, not the municipality choropleth underneath),
      // munis otherwise (so ordinary scroll-browsing through that band --
      // never having touched the Parcel button -- looks exactly as it
      // always has, since that's an existing, already-shipped feature this
      // change must not regress). Above z13 parcels always win regardless
      // of activeLevel (munis-fill's own maxzoom:13 already hides it there
      // natively); that part is unchanged from before this widening.
      const updateTierVisibility = () => {
        const parcelMode = activeLevelRef.current === 'parcel'
        const showParcels = parcelMode || map.getZoom() >= 13
        map.setLayoutProperty('parcels-fill', 'visibility', showParcels ? 'visible' : 'none')
        map.setLayoutProperty('parcels-outline', 'visibility', showParcels ? 'visible' : 'none')
        map.setLayoutProperty('munis-fill', 'visibility', parcelMode ? 'none' : 'visible')
        map.setLayoutProperty('munis-outline', 'visibility', parcelMode ? 'none' : 'visible')
        // Test-observability only (same idiom as data-zoom below).
        // data-parcels-visible reflects this function's own *intent* --
        // useful, but on its own it would pass even against a stale
        // tileset that still stops at its old z13 minzoom, since
        // visibility is just a layout property, not proof of actual data.
        // data-parcels-have-data queries what's actually rendered right
        // now, which is the real proof: lets e2e tests confirm the actual
        // bug this widening fixed -- that picking Parcel and scrolling out
        // shows real parcel geometry, not a silent fallback to the
        // municipality choropleth (or an equally silent blank layer if the
        // tileset were still too narrow) -- without fragile canvas-pixel
        // inspection.
        containerRef.current?.setAttribute('data-parcels-visible', String(showParcels))
        containerRef.current?.setAttribute(
          'data-parcels-have-data',
          String(map.queryRenderedFeatures({ layers: ['parcels-fill'] }).length > 0),
        )
      }
      updateTierVisibilityRef.current = updateTierVisibility
      updateTierVisibility()

      // Test-observability only, not read by any app code: the detail-level
      // toggle deliberately doesn't react to live zoom (it's a sticky
      // "last explicit choice" indicator, not a status readout -- see
      // SearchMapView.tsx), so e2e tests need some other way to confirm
      // the zoom-floor enforcement itself still works. Reported on every
      // 'zoom' tick, not just 'zoomend' -- 'zoomend' only fires once a
      // gesture fully settles, which reads as "stuck" to a test polling
      // mid-scroll.
      const reportZoom = () => {
        if (!containerRef.current) return
        containerRef.current.setAttribute('data-zoom', String(map.getZoom()))
        containerRef.current.setAttribute('data-min-zoom', String(map.getMinZoom()))
      }
      reportZoom()
      map.on('zoom', reportZoom)
      map.on('zoom', updateTierVisibility)
    })

    return () => {
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Global filters -> MapLibre filter expression on the parcels layer.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const apply = () => {
      if (!map.getLayer('parcels-fill')) return
      const clauses: ExpressionSpecification[] = []
      if (filters.classGroups.length) {
        clauses.push(['in', ['get', 'class_group'], ['literal', filters.classGroups]] as ExpressionSpecification)
      }
      if (filters.bands.length) {
        clauses.push(['in', ['get', 'band'], ['literal', filters.bands]] as ExpressionSpecification)
      }
      if (filters.lens === 'current') clauses.push(['==', ['get', 'cur'], true] as ExpressionSpecification)
      if (filters.lens === 'future') clauses.push(['==', ['get', 'fut'], true] as ExpressionSpecification)
      if (filters.lens === 'either') {
        clauses.push(['any', ['==', ['get', 'cur'], true], ['==', ['get', 'fut'], true]] as ExpressionSpecification)
      }
      if (filters.minOverlapPct > 0) {
        const frac = filters.minOverlapPct / 100
        const overlapExpr: ExpressionSpecification = ['max', ['get', 'sfha_pct'], ['coalesce', ['get', 'fut_pct'], 0]]
        clauses.push(['>=', overlapExpr, frac] as unknown as ExpressionSpecification)
      }
      if (filters.minAssessedValue > 0) {
        clauses.push(['>=', ['coalesce', ['get', 'net_value'], 0], filters.minAssessedValue] as ExpressionSpecification)
      }
      const filterExpr: ExpressionSpecification | null =
        clauses.length === 0 ? null : (clauses.length === 1 ? clauses[0] : (['all', ...clauses] as ExpressionSpecification))
      map.setFilter('parcels-fill', filterExpr)
      map.setFilter('parcels-outline', filterExpr)

      const lensLayers: [string, 'current' | 'future' | 'either'][] = [
        ['counties-fill', filters.lens], ['munis-fill', filters.lens],
      ]
      for (const [layerId, lens] of lensLayers) {
        if (map.getLayer(layerId)) map.setPaintProperty(layerId, 'fill-color', choroplethExpr(lens))
      }
    }
    if (map.loaded()) apply()
    else map.once('load', apply)
  }, [filters])

  useEffect(() => {
    const map = mapRef.current
    if (!flyTo || !map) return
    const targetZoom = flyTo.zoom ?? 15.5
    const selectAtTarget = () => {
      // After flying in (past minzoom:13), query the parcel actually
      // rendered at that point so a search result opens the same detail
      // panel a direct map click would -- not just centers the map.
      const point = map.project([flyTo.lon, flyTo.lat])
      const hits = map.queryRenderedFeatures(point, { layers: ['parcels-fill'] })
      if (hits[0]) onParcelClick(hits[0].properties as ParcelTileProps)
    }
    map.flyTo({ center: [flyTo.lon, flyTo.lat], zoom: targetZoom })
    map.once('idle', selectAtTarget)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flyTo])

  useEffect(() => {
    const map = mapRef.current
    if (!zoomTo || !map) return
    // Set the floor before moving, not after -- otherwise there's a window
    // right after the click where an in-flight scroll could still drop
    // below the new floor before it takes effect.
    map.setMinZoom(zoomTo.minZoom)
    map.easeTo({ zoom: zoomTo.zoom })
  }, [zoomTo])

  // Re-run the visibility swap the instant activeLevel changes (a button
  // click), rather than waiting for the next 'zoom' event the easeTo above
  // will soon fire anyway -- avoids a brief flash of the wrong layer.
  useEffect(() => {
    updateTierVisibilityRef.current()
  }, [activeLevel])

  return (
    <div
      ref={containerRef}
      role="application"
      aria-label="Statewide flood risk map"
      // overflow-hidden, not just rounded-lg: without it the border curves
      // but the map canvas underneath stays rectangular, poking past the
      // rounded corners.
      className="h-[70vh] w-full overflow-hidden rounded-lg border border-zinc-200 shadow-sm dark:border-zinc-800 dark:shadow-none"
    />
  )
}
