import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

// §12.2: "Axe: zero serious violations". Checked on every top-level view,
// both with default (statewide) filters and with a real geography selected
// (county/muni selects, search results, and the parcel detail panel only
// exist once data is loaded -- scanning only the empty default state would
// silently skip most of the actual UI).
const VIEWS = [
  { path: '/', name: 'Search & Map' },
  { path: '/summary', name: 'Jurisdiction Summary' },
  { path: '/exposure', name: 'District Exposure' },
  { path: '/ranked', name: 'Ranked Municipalities' },
  { path: '/methodology', name: 'Methodology' },
]

for (const view of VIEWS) {
  test(`${view.name}: zero serious/critical axe violations (default state)`, async ({ page }) => {
    await page.goto(view.path)
    await page.waitForLoadState('networkidle')
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
    const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([])
  })
}

test('Search & Map + Ranked Municipalities: zero serious/critical axe violations with a real geography selected', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('County').selectOption({ value: '029' })
  await page.getByLabel('Municipality').selectOption({ value: '02902' })
  await page.getByLabel('Search address, PIN, or block/lot').fill('1502_49_18')
  // Scoped to the results listbox specifically: an unscoped getByRole('option')
  // also matches native <select><option> elements (they carry an implicit
  // option role even while their dropdown is closed), and those precede the
  // search box in DOM order, so an unscoped .first() grabs one of those instead.
  await expect(
    page.getByRole('listbox', { name: 'Search results' }).getByRole('option').first(),
  ).toBeVisible()

  const searchResults = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
  const seriousSearch = searchResults.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(seriousSearch, JSON.stringify(seriousSearch, null, 2)).toEqual([])

  await page.goto('/ranked')
  await page.getByLabel('County').selectOption({ value: '029' })
  await expect(page.getByRole('table')).toBeVisible()

  const rankedResults = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
  const seriousRanked = rankedResults.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(seriousRanked, JSON.stringify(seriousRanked, null, 2)).toEqual([])
})
