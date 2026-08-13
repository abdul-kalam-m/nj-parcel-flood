import { DATA_BASE_URL } from '../config'
import type {
  GeographyIndex, GeographySummary, RankedMuniEntry, SearchRecord,
} from '../types'

// Simple in-memory response cache -- these files are static per pipeline
// run (§6.4: refreshed manually, annually/quarterly), so there's no reason
// to re-fetch the same summary twice in one session.
const cache = new Map<string, Promise<unknown>>()

function getJSON<T>(path: string): Promise<T> {
  const url = `${DATA_BASE_URL}${path}`
  if (!cache.has(url)) {
    cache.set(
      url,
      fetch(url).then((r) => {
        if (!r.ok) throw new Error(`${r.status} fetching ${url}`)
        return r.json() as Promise<T>
      }),
    )
  }
  return cache.get(url) as Promise<T>
}

export function fetchGeographyIndex(): Promise<GeographyIndex> {
  return getJSON('/geography_index.json')
}

export function fetchStateSummary(): Promise<GeographySummary> {
  return getJSON('/summaries/state.json')
}

export function fetchCountySummary(fips: string): Promise<GeographySummary> {
  return getJSON(`/summaries/county/${fips}.json`)
}

export function fetchMuniSummary(fipsMun: string): Promise<GeographySummary> {
  return getJSON(`/summaries/muni/${fipsMun}.json`)
}

export function fetchRankedMunicipalities(): Promise<RankedMuniEntry[]> {
  return getJSON('/ranked_municipalities.json')
}

// Search shards are gzipped; the browser's fetch decompresses transparently
// when the server sends Content-Encoding: gzip, but these are served as
// plain octet-stream (they're pre-gzipped *files*, §7.1's ".json.gz"), so
// decompress with DecompressionStream ourselves.
const searchCache = new Map<string, Promise<SearchRecord[]>>()

export function fetchSearchShard(fips: string, mun2: string): Promise<SearchRecord[]> {
  const url = `${DATA_BASE_URL}/search/${fips}/${mun2}.json.gz`
  if (!searchCache.has(url)) {
    searchCache.set(
      url,
      fetch(url)
        .then((r) => {
          if (!r.ok) throw new Error(`${r.status} fetching ${url}`)
          if (!r.body) throw new Error('no response body')
          const ds = new DecompressionStream('gzip')
          return new Response(r.body.pipeThrough(ds)).json()
        }) as Promise<SearchRecord[]>,
    )
  }
  return searchCache.get(url) as Promise<SearchRecord[]>
}
