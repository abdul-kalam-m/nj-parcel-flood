import { defineConfig, devices } from '@playwright/test'

// §12.2 "Web checks": Playwright (search by PIN -> panel; county->muni filter
// cascades; district chart matches summary JSON; export downloads with
// disclaimer) + Axe (zero serious violations). Runs against the real dev
// server (real artifacts/ data via vite.config.ts's serveArtifacts plugin,
// not mocks) -- Playwright drives its own bundled browser, independent of
// the Claude Code preview pane that some earlier manual verification in this
// project hit a compositing limitation with (PROGRESS.md 2026-08-13).
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
