import { test, expect } from '@playwright/test'

// §12.2: "Playwright: search by PIN -> panel". Real data throughout: Barnegat
// Light Boro (Ocean County, 029/02902), pin 1502_49_18 -- confirmed present
// in the actual committed search shard before writing this test, not assumed.
test('search by PIN opens the parcel detail panel', async ({ page }) => {
  await page.goto('/')

  await page.getByLabel('County').selectOption({ value: '029' })
  await page.getByLabel('Municipality').selectOption({ value: '02902' })

  const search = page.getByLabel('Search address, PIN, or block/lot')
  await search.fill('1502_49_18')

  // role="option" lives on the result <button> itself (not a wrapping <li>)
  // so axe doesn't flag nested interactive controls -- `result` below
  // resolves directly to that button, so it's clicked directly, not via a
  // nested getByRole('button').
  const result = page.getByRole('option').filter({ hasText: '1502_49_18' })
  await expect(result).toBeVisible()
  await result.click()

  const panel = page.getByRole('complementary', { name: 'Parcel detail' })
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('1502_49_18')
  await expect(panel).toContainText('Score drivers')
  await expect(panel).toContainText('C_cur (current)')
  await expect(panel).toContainText('C_fut (future)')
  await expect(panel).toContainText('C_loss (tract history)')
})
