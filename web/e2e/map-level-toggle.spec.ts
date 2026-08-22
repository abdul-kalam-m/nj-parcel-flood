import { test, expect } from '@playwright/test'

// New "map detail level" toggle. This session's preview pane can't confirm
// animated MapLibre camera moves (documented for flyTo -- easeTo turned out
// to hit the same limitation, per PROGRESS.md), so a real-browser check is
// the actual proof the zoom change -> 'zoomend' -> button-state chain works.
test('map level toggle changes on click, and stays put through scrolling', async ({ page }) => {
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

  // Owner feedback: after clicking Parcel, scrolling out used to flip the
  // toggle to "Municipality" once the camera crossed that zoom threshold --
  // read as the map second-guessing the user's own explicit choice. The
  // toggle is now sticky (only an explicit click changes it), so a scroll
  // that would clearly cross multiple tier boundaries if it were still
  // reactive must leave "Parcel" pressed.
  await scrollMap(page, 100, 30)
  await expect(parcel).toHaveAttribute('aria-pressed', 'true')
  await expect(muni).toHaveAttribute('aria-pressed', 'false')
})

// Picking a level sets it as the map's zoom floor: scrolling *out* can't
// cross back into a lower tier, scrolling *in* is never restricted. The
// toggle's own pressed state no longer reflects live zoom (see the test
// above), so these read the map's actual current zoom via the data-zoom
// attribute MapCanvas.tsx exposes for exactly this purpose. Empirically
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

async function currentZoom(page: import('@playwright/test').Page): Promise<number> {
  const mapRegion = page.getByRole('application', { name: 'Statewide flood risk map' })
  const attr = await mapRegion.getAttribute('data-zoom')
  return Number(attr)
}

test('picking Municipality blocks scrolling out below its own floor, but scrolling in still works', async ({ page }) => {
  await page.goto('/')
  const group = page.getByRole('group', { name: 'Map detail level' })
  const muni = group.getByRole('button', { name: 'Municipality' })

  await muni.click()
  await expect(muni).toHaveAttribute('aria-pressed', 'true')

  await scrollMap(page, 100) // scroll out -- would clearly cross below the floor (9) unrestricted
  await expect(async () => {
    expect(await currentZoom(page)).toBeGreaterThanOrEqual(9)
  }).toPass()

  await scrollMap(page, -100, 30) // scroll in -- must still be free to move well past 13
  await expect(async () => {
    expect(await currentZoom(page)).toBeGreaterThan(13)
  }).toPass()
})

test('picking Parcel blocks scrolling out below its own floor (shared with Municipality)', async ({ page }) => {
  await page.goto('/')
  const group = page.getByRole('group', { name: 'Map detail level' })
  const parcel = group.getByRole('button', { name: 'Parcel' })

  await parcel.click()
  await expect(parcel).toHaveAttribute('aria-pressed', 'true')

  // Parcel shares Municipality's floor (9), not its own render threshold
  // (13, parcels-fill's minzoom) -- owner feedback: locking zoom-out at 13
  // felt too tight, since zooming out from one parcel to see its
  // surrounding municipality is a reasonable thing to want.
  await scrollMap(page, 100) // moderate scroll -- crosses below 13, must not be blocked yet
  await expect(async () => {
    const z = await currentZoom(page)
    expect(z).toBeLessThan(13)
    expect(z).toBeGreaterThanOrEqual(9)
  }).toPass()

  await scrollMap(page, 100, 30) // wide margin -- would clearly cross below 9 unrestricted
  await expect(async () => {
    expect(await currentZoom(page)).toBeGreaterThanOrEqual(9)
  }).toPass()
})
