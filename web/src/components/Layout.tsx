import { NavLink, Outlet } from 'react-router-dom'
import { DISCLAIMER } from '../config'
import { FilterBar } from './FilterBar'

const NAV_ITEMS = [
  { to: '/', label: 'Search & Map' },
  { to: '/summary', label: 'Jurisdiction Summary' },
  { to: '/exposure', label: 'District Exposure' },
  { to: '/ranked', label: 'Ranked Municipalities' },
  { to: '/methodology', label: 'Methodology' },
]

// Simple original geometric droplet mark -- not a copy of any existing
// brand/logo, just a generic water-themed glyph giving the wordmark some
// visual identity beyond plain text (§ owner: "UI overhaul").
function DropletMark() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="shrink-0 text-brand-700 dark:text-brand-400">
      <path d="M12 2.5C8.5 8 4.5 12.8 4.5 16.5a7.5 7.5 0 0015 0c0-3.7-4-8.5-7.5-14z" fill="currentColor" />
    </svg>
  )
}

export function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-brand-700 focus:px-3 focus:py-2 focus:text-white"
      >
        Skip to main content
      </a>
      {/* Sticky: the filter bar lives inside this header, and stays useful
          on long pages (Methodology, a 20+ row Ranked Municipalities table)
          instead of scrolling out of reach. */}
      <header className="sticky top-0 z-20 border-b border-zinc-200 bg-white/95 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-950/95">
        <div className="mx-auto max-w-7xl px-4 py-3">
          <h1 className="flex items-center gap-2 text-xl font-bold tracking-tight">
            <DropletMark />
            NJ Parcel Flood Risk Dashboard
          </h1>
          <nav aria-label="Main views" className="mt-2 flex flex-wrap gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `rounded-full px-3 py-1.5 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-brand-700 text-white'
                      : 'text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <FilterBar />
      </header>

      <main id="main-content" className="mx-auto w-full max-w-7xl flex-1 px-4 py-4">
        <Outlet />
      </main>

      <footer className="border-t border-zinc-200 bg-zinc-50 px-4 py-3 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        <p className="mx-auto max-w-7xl">
          <strong>Screening tool — not a flood determination.</strong> {DISCLAIMER.replace('Screening tool — not a flood determination. ', '')}
        </p>
      </footer>
    </div>
  )
}
