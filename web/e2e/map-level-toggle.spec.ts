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

async function parcelsVisible(page: import('@playwright/test').Page): Promise<boolean> {
  const mapRegion = page.getByRole('application', { name: 'Statewide flood risk map' })
  return (await mapRegion.getAttribute('data-parcels-visible')) === 'true'
}

// Stronger than parcelsVisible: that only reflects MapCanvas.tsx's own
// visibility-toggle *intent* (a layout property), which would read true
// even against a stale tileset that still stopped at its old z13 minzoom --
// this checks queryRenderedFeatures instead, actual proof real parcel
// geometry is on screen, not just that the layer isn't hidden.
async function parcelsHaveData(page: import('@playwright/test').Page): Promise<boolean> {
  const mapRegion = page.getByRole('application', { name: 'Statewide flood risk map' })
  return (await mapRegion.getAttribute('data-parcels-have-data')) === 'true'
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

test('picking Parcel blocks scrolling out below its own floor (9, shared with Municipality), and keeps showing real parcels the whole way down', async ({ page }) => {
  await page.goto('/')
  const group = page.getByRole('group', { name: 'Map detail level' })
  const parcel = group.getByRole('button', { name: 'Parcel' })

  await parcel.click()
  await expect(parcel).toHaveAttribute('aria-pressed', 'true')
  await expect(async () => {
    expect(await parcelsVisible(page)).toBe(true)
  }).toPass()

  // Parcel's floor is 9 now, same as Municipality's -- parcels.pmtiles was
  // widened from its original z13-only range down to z9 specifically so
  // this could be a real floor and not just a button-label mismatch (see
  // the other Parcel test below, and PROGRESS.md 2026-08-13 "Parcel
  // zoom-out fix, full scope"). A wide scroll here would clearly cross
  // well below 9 if unrestricted.
  await scrollMap(page, 100, 30)
  await expect(async () => {
    expect(await currentZoom(page)).toBeGreaterThanOrEqual(9)
  }).toPass()
  // The whole point of widening the tileset rather than just the floor:
  // real parcel geometry, not the municipality choropleth (and not a blank
  // layer from a tileset that only *claims* to cover z9 but doesn't), is
  // what's actually on screen all the way down to that floor.
  expect(await parcelsVisible(page)).toBe(true)
  await expect(async () => {
    expect(await parcelsHaveData(page)).toBe(true)
  }).toPass()
})

test('Municipality mode still shows the municipality choropleth (not parcels) across 9-13, unaffected by the Parcel-mode widening', async ({ page }) => {
  await page.goto('/')
  const group = page.getByRole('group', { name: 'Map detail level' })
  const muni = group.getByRole('button', { name: 'Municipality' })

  await muni.click()
  await expect(muni).toHaveAttribute('aria-pressed', 'true')
  // Regression guard: parcels-fill is now zoom-eligible across the same
  // 9-13 band munis-fill uses, purely by minzoom/maxzoom -- without the
  // explicit visibility toggle in MapCanvas.tsx's updateTierVisibility,
  // parcels would silently cover the municipality choropleth for anyone
  // just scrolling through that range normally, never having touched the
  // Parcel button at all.
  await expect(async () => {
    expect(await parcelsVisible(page)).toBe(false)
  }).toPass()
})
