import { NavLink, Outlet } from 'react-router-dom'
import { DISCLAIMER } from '../config'
import { FilterBar } from './FilterBar'

const NAV_ITEMS = [
  { to: '/', label: 'Search & Map' },
  { to: '/summary', label: 'Jurisdiction Summary' },
  { to: '/exposure', label: 'District Exposure' },
  { to: '/ranked', label: 'Ranked Municipalities' },
]

export function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-blue-700 focus:px-3 focus:py-2 focus:text-white"
      >
        Skip to main content
      </a>
      <header className="border-b border-zinc-200 dark:border-zinc-800">
        <div className="mx-auto max-w-7xl px-4 py-3">
          <h1 className="text-lg font-semibold">NJ Parcel Flood Risk Dashboard</h1>
          <nav aria-label="Main views" className="mt-2 flex flex-wrap gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `rounded px-3 py-1.5 text-sm font-medium ${
                    isActive
                      ? 'bg-blue-700 text-white'
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
