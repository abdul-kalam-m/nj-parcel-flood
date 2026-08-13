import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import fs from 'node:fs'
import type { Plugin } from 'vite'

// Serves the repo's artifacts/ directory at /data/* during dev, mirroring
// where these files live in production (Cloudflare R2, public bucket, CORS
// enabled -- OPERATING_GUIDE.md §7.1/§6.2). Production build reads
// VITE_DATA_BASE_URL instead (see src/config.ts); this plugin never ships,
// dev-only via configureServer.
function serveArtifacts(): Plugin {
  const artifactsDir = path.resolve(import.meta.dirname, '../artifacts')
  const mimeTypes: Record<string, string> = {
    '.json': 'application/json',
    '.gz': 'application/gzip',
    '.pmtiles': 'application/octet-stream',
    '.parquet': 'application/octet-stream',
  }
  return {
    name: 'serve-artifacts',
    configureServer(server) {
      server.middlewares.use('/data', (req, res, next) => {
        const reqPath = decodeURIComponent((req.url || '').split('?')[0])
        const filePath = path.join(artifactsDir, reqPath)
        if (!filePath.startsWith(artifactsDir)) {
          res.statusCode = 403
          res.end('Forbidden')
          return
        }
        fs.stat(filePath, (err, stat) => {
          if (err || !stat.isFile()) {
            next()
            return
          }
          const ext = path.extname(filePath)
          res.setHeader('Content-Type', mimeTypes[ext] || 'application/octet-stream')
          res.setHeader('Access-Control-Allow-Origin', '*')
          // PMTiles reads specific byte ranges out of a multi-hundred-MB
          // archive rather than downloading the whole file -- Range support
          // here isn't optional, the map won't load without it.
          const range = req.headers.range
          if (range) {
            const [startStr, endStr] = range.replace(/bytes=/, '').split('-')
            const start = parseInt(startStr, 10)
            const end = endStr ? parseInt(endStr, 10) : stat.size - 1
            res.statusCode = 206
            res.setHeader('Content-Range', `bytes ${start}-${end}/${stat.size}`)
            res.setHeader('Accept-Ranges', 'bytes')
            res.setHeader('Content-Length', String(end - start + 1))
            fs.createReadStream(filePath, { start, end }).pipe(res)
          } else {
            res.setHeader('Accept-Ranges', 'bytes')
            res.setHeader('Content-Length', String(stat.size))
            fs.createReadStream(filePath).pipe(res)
          }
        })
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), serveArtifacts()],
  server: {
    fs: { allow: ['..'] },
  },
  // maplibre-gl spawns its own worker via new Worker(new URL(...)) --
  // esbuild's dependency pre-bundling doesn't preserve that reference
  // correctly in dev mode (the worker chunk 404s), a known maplibre-gl +
  // Vite incompatibility. Excluding it from pre-bundling serves it as
  // native ESM instead, which resolves the worker URL correctly.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
})
