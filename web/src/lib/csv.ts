import { DISCLAIMER } from '../config'
import { DATA_BASE_URL } from '../config'

interface Meta {
  vintages: Record<string, string>
}

let metaPromise: Promise<Meta | null> | null = null
function loadMeta(): Promise<Meta | null> {
  if (!metaPromise) {
    metaPromise = fetch(`${DATA_BASE_URL}/meta.json`)
      .then((r) => (r.ok ? (r.json() as Promise<Meta>) : null))
      .catch(() => null)
  }
  return metaPromise
}

// §7.2: "Exports: CSV of any visible table with disclaimer header + vintages."
// §5.7: disclaimer verbatim, restyle only -- kept word-for-word here too.
// §6.4: "Each rerun bumps meta.json vintages; the UI shows them" -- exports
// embed the real per-source retrieval dates, not a pointer to another file.
export async function downloadCsv(filename: string, rows: Record<string, string | number>[]) {
  if (rows.length === 0) return
  const meta = await loadMeta()
  const vintageLine = meta
    ? `Data vintages: ${Object.entries(meta.vintages).map(([k, v]) => `${k}=${v}`).join(', ')}`
    : 'Data vintages: unavailable'

  const headers = Object.keys(rows[0])
  const escape = (v: string | number) => {
    const s = String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [
    `# ${DISCLAIMER}`,
    `# ${vintageLine}`,
    headers.join(','),
    ...rows.map((r) => headers.map((h) => escape(r[h])).join(',')),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
