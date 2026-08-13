import { test, expect } from '@playwright/test'
import { DISCLAIMER } from '../src/disclaimer'

// §12.2: "export downloads with disclaimer". §5.7: disclaimer verbatim.
test('jurisdiction summary CSV export includes the verbatim disclaimer and real vintages', async ({ page }) => {
  await page.goto('/summary')

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export CSV' }).click()
  const download = await downloadPromise

  expect(download.suggestedFilename()).toMatch(/^jurisdiction-summary-.*\.csv$/)

  const stream = await download.createReadStream()
  const chunks: Buffer[] = []
  for await (const chunk of stream) chunks.push(chunk as Buffer)
  const content = Buffer.concat(chunks).toString('utf-8')

  expect(content).toContain(DISCLAIMER)
  expect(content).toMatch(/^# .*Screening tool/)
  expect(content).toContain('Data vintages:')
  expect(content).toContain('geography,class_group,lens,parcel_count')
})
