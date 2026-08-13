import { test, expect } from '@playwright/test'

// §12.2: "county->muni filter cascades".
test('selecting a county populates and enables the municipality filter, scoped to that county', async ({ page }) => {
  await page.goto('/')

  const muniSelect = page.getByLabel('Municipality')
  await expect(muniSelect).toBeDisabled()

  await page.getByLabel('County').selectOption({ value: '029' }) // Ocean
  await expect(muniSelect).toBeEnabled()
  await expect(muniSelect.getByRole('option', { name: 'BARNEGAT LIGHT BORO' })).toHaveCount(1)
  // a muni from a *different* county must not leak into this list
  await expect(muniSelect.getByRole('option', { name: 'NEWARK CITY' })).toHaveCount(0)

  await muniSelect.selectOption({ value: '02902' })
  await expect(muniSelect).toHaveValue('02902')

  // changing county again must reset the (now stale) muni selection, not
  // silently keep showing a muni that belongs to the old county
  await page.getByLabel('County').selectOption({ value: '013' }) // Essex
  await expect(muniSelect).toHaveValue('')
  await expect(muniSelect.getByRole('option', { name: 'NEWARK CITY' })).toHaveCount(1)
})

test('jurisdiction summary reflects the selected geography, not statewide, once a muni is chosen', async ({ page }) => {
  await page.goto('/summary')
  await expect(page.getByRole('heading', { name: /Jurisdiction summary/ })).toContainText('New Jersey (statewide)')

  await page.getByLabel('County').selectOption({ value: '029' })
  await expect(page.getByRole('heading', { name: /Jurisdiction summary/ })).toContainText('OCEAN')

  await page.getByLabel('Municipality').selectOption({ value: '02902' })
  await expect(page.getByRole('heading', { name: /Jurisdiction summary/ })).toContainText('BARNEGAT LIGHT BORO')
})
