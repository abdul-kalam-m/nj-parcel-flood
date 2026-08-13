import { test, expect } from '@playwright/test'

interface ClassGroupStats {
  pct_at_risk: number
  parcel_count: number
}
interface GeographySummary {
  current: Record<string, ClassGroupStats>
  future: Record<string, ClassGroupStats>
}

// §12.2: "district chart matches summary JSON" -- fetches the same source
// file the app itself renders from and checks the *displayed* numbers
// against it, not just that a chart exists.
test('district exposure table matches artifacts/summaries/county/029.json exactly', async ({ page, request }) => {
  const res = await request.get('/data/summaries/county/029.json')
  expect(res.ok()).toBeTruthy()
  const summary = (await res.json()) as GeographySummary

  await page.goto('/exposure')
  await page.getByLabel('County').selectOption({ value: '029' })

  const table = page.getByRole('table')
  await expect(table).toBeVisible()

  for (const classGroup of Object.keys(summary.current)) {
    if (classGroup === 'ALL') continue
    const row = table.locator('tbody tr', { hasText: classGroup })
    const cells = row.locator('td')
    const expectedCurrentPct = `${summary.current[classGroup].pct_at_risk.toFixed(1)}%`
    const expectedFuturePct = `${(summary.future[classGroup]?.pct_at_risk ?? 0).toFixed(1)}%`
    await expect(cells.nth(1)).toHaveText(expectedCurrentPct)
    await expect(cells.nth(2)).toHaveText(expectedFuturePct)
    await expect(cells.nth(3)).toHaveText(String(summary.current[classGroup].parcel_count))
  }
})
