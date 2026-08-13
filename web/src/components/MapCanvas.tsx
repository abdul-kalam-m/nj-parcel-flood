import { useEffect, useRef } from 'react'
import {
  MapLibreMap, NavigationControl, addProtocol,
  type ExpressionSpecification, type MapLayerMouseEvent,
} from 'maplibre-gl'
import { Protocol } from 'pmtiles'
import { DATA_BASE_URL } from '../config'
import { useFilters } from '../context/useFilters'
import { BAND_MATCH_EXPRESSION } from '../lib/bands'
import type { ParcelTileProps } from '../types'

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

export interface MapCanvasProps {
  onParcelClick: (props: ParcelTileProps) => void
  flyTo?: { lon: number; lat: number; zoom?: number } | null
}

export function MapCanvas({ onParcelClick, flyTo }: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const { filters } = useFilters()

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
        minzoom: 13,
        paint: { 'fill-color': BAND_MATCH_EXPRESSION as unknown as ExpressionSpecification, 'fill-opacity': 0.8 },
      })
      map.addLayer({
        id: 'parcels-outline', type: 'line', source: 'parcels', 'source-layer': 'parcels',
        minzoom: 13,
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

  return (
    <div
      ref={containerRef}
      role="application"
      aria-label="Statewide flood risk map"
      className="h-[70vh] w-full rounded border border-zinc-200 dark:border-zinc-800"
    />
  )
}
