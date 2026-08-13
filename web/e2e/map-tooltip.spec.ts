import { test, expect } from '@playwright/test'

// Map hover tooltip. This session's preview pane never gets past MapLibre's
// 'load' event (no frame compositing -> no tile requests at all), so this
// is the only way to actually confirm the tooltip renders against real,
// asynchronously-loaded boundary tiles.
test('hovering the map shows a tooltip with county name and %-at-risk', async ({ page }) => {
  await page.goto('/')
  const mapRegion = page.getByRole('application', { name: 'Statewide flood risk map' })
  await expect(mapRegion).toBeVisible()
  const box = await mapRegion.boundingBox()
  if (!box) throw new Error('map region has no bounding box')
  const cx = box.x + box.width / 2
  const cy = box.y + box.height / 2

  // Tiles load asynchronously after 'load' fires, so poll with genuinely
  // new mouse positions (MapLibre only re-queries on an actual move event)
  // until a boundary feature is rendered under the cursor.
  const popup = page.locator('.maplibregl-popup')
  for (let i = 0; i < 20; i++) {
    await page.mouse.move(cx + (i % 2), cy)
    if (await popup.isVisible()) break
    await page.waitForTimeout(500)
  }
  await expect(popup).toBeVisible()
  await expect(popup).toContainText('at risk')
})
