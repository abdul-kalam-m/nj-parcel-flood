// P8: NJ's own statewide geocoder (§4/§6.1 -- "client geocode (P8) only",
// called directly from the browser, no backend proxy). CORS verified live
// (fetch from a localhost:5173 origin succeeds with real candidates) before
// building against it, not assumed.
const P8_GEOCODER_URL = 'https://geo.nj.gov/arcgis/rest/services/Tasks/NJ_Geocode/GeocodeServer'

// Esri locator scores run 0-100 (100 = exact match); below ~60 a candidate
// is more often noise than a real match -- a UI judgment call, not a
// correctness threshold, easy to retune if it proves too strict/loose live.
const MIN_SCORE = 60
const MAX_CANDIDATES = 5

export interface GeocodeCandidate {
  address: string
  lon: number
  lat: number
  score: number
}

interface RawCandidate {
  address: string
  score: number
  location: { x: number; y: number }
}

// §7.2: "search bar (address via P8 geocode -> point -> parcel hit ...)" --
// this returns the point; the caller flies the map there and queries
// whatever parcel is actually rendered at that point, the same path a
// PIN/block-lot search result already uses.
export async function geocodeAddress(
  query: string,
  signal?: AbortSignal,
): Promise<GeocodeCandidate[]> {
  const url = `${P8_GEOCODER_URL}/findAddressCandidates?${new URLSearchParams({
    SingleLine: query,
    f: 'json',
    outSR: '4326',
    maxLocations: String(MAX_CANDIDATES),
  })}`
  try {
    const r = await fetch(url, { signal })
    if (!r.ok) return []
    const data = (await r.json()) as { candidates?: RawCandidate[] }
    return (data.candidates ?? [])
      .filter((c) => c.score >= MIN_SCORE)
      .map((c) => ({ address: c.address, lon: c.location.x, lat: c.location.y, score: c.score }))
  } catch {
    // Network failure, abort (debounce superseded this call), or a
    // malformed response -- fail quiet. A geocoder hiccup shouldn't break
    // the rest of the search bar (the local shard path still works).
    return []
  }
}
