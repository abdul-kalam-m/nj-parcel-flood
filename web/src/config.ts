// Dev: served locally by vite.config.ts's serveArtifacts plugin from ../artifacts.
// Prod: Cloudflare R2 public bucket (§6.2/§7.1) -- set at build time.
export const DATA_BASE_URL: string =
  (import.meta.env.VITE_DATA_BASE_URL as string | undefined) ?? '/data'

export { DISCLAIMER } from './disclaimer'
