import { test, expect } from '@playwright/test'

// New "map detail level" toggle. This session's preview pane can't confirm
// animated MapLibre camera moves (documented for flyTo -- easeTo turned out
// to hit the same limitation, per PROGRESS.md), so a real-browser check is
// the actual proof the zoom change -> 'zoomend' -> button-state chain works.
test('map level toggle changes the active tier as the map camera moves', async ({ page }) => {
  await page.goto('/')
  const group = page.getByRole('group', { name: 'Map detail level' })
  const county = group.getByRole('button', { name: 'County' })
  const muni = group.getByRole('button', { name: 'Municipality' })
  const parcel = group.getByRole('button', { name: 'Parcel' })

  await expect(county).toHaveAttribute('aria-pressed', 'true')

  await muni.click()
  await expect(muni).toHaveAttribute('aria-pressed', 'true')
  await expect(county).toHaveAttribute('aria-pressed', 'false')

  await parcel.click()
  await expect(parcel).toHaveAttribute('aria-pressed', 'true')
  await expect(muni).toHaveAttribute('aria-pressed', 'false')
})
