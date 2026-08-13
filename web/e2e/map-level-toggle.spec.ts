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

// Picking a level sets it as the map's zoom floor: scrolling *out* can't
// cross back into a lower tier, scrolling *in* is never restricted. Empirically
// confirmed (via a temporary window.__debugMap hook, since removed) that
// Playwright's synthetic wheel events move MapLibre's zoom by ~0.15 per 100
// deltaY units -- tick counts below are each a >2x safety margin over the
// minimum needed to cross the relevant threshold, tuned down from an
// initial, much larger guess after that guess made this file heavy enough
// to contend with other tests for CPU under full parallelism (search-by-
// pin.spec.ts intermittently missed its own 5s timeout as a result -- see
// PROGRESS.md).
async function scrollMap(page: import('@playwright/test').Page, deltaY: number, ticks = 20) {
  const mapRegion = page.getByRole('application', { name: 'Statewide flood risk map' })
  const box = await mapRegion.boundingBox()
  if (!box) throw new Error('map region has no bounding box')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  for (let i = 0; i < ticks; i++) await page.mouse.wheel(0, deltaY)
}

test('picking Municipality blocks scrolling out to County, but scrolling in still works', async ({ page }) => {
  await page.goto('/')
  const group = page.getByRole('group', { name: 'Map detail level' })
  const county = group.getByRole('button', { name: 'County' })
  const muni = group.getByRole('button', { name: 'Municipality' })
  const parcel = group.getByRole('button', { name: 'Parcel' })

  await muni.click()
  await expect(muni).toHaveAttribute('aria-pressed', 'true')

  await scrollMap(page, 100) // scroll out -- would clearly cross below the county threshold unrestricted
  await expect(muni).toHaveAttribute('aria-pressed', 'true')
  await expect(county).toHaveAttribute('aria-pressed', 'false')

  await scrollMap(page, -100, 30) // scroll in -- must still be free to cross up into Parcel (needs a wider margin: floor 9 -> past 13)
  await expect(parcel).toHaveAttribute('aria-pressed', 'true')
})

test('picking Parcel blocks scrolling out to Municipality', async ({ page }) => {
  await page.goto('/')
  const group = page.getByRole('group', { name: 'Map detail level' })
  const muni = group.getByRole('button', { name: 'Municipality' })
  const parcel = group.getByRole('button', { name: 'Parcel' })

  await parcel.click()
  await expect(parcel).toHaveAttribute('aria-pressed', 'true')

  await scrollMap(page, 100)
  await expect(parcel).toHaveAttribute('aria-pressed', 'true')
  await expect(muni).toHaveAttribute('aria-pressed', 'false')
})
