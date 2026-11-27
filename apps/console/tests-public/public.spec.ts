import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', route => route.abort())
  await page.route('**/workload-api/**', route => route.abort())
  await page.route('**/prometheus/**', route => route.abort())
})

test('public landing launches a backend-independent verified replay', async ({ page }) => {
  await page.goto('./')
  await expect(page.getByRole('heading', { name: 'CloudShift DB' })).toBeVisible()
  await page.getByRole('link', { name: 'Launch Interactive Migration Demo' }).click()
  await expect(page).toHaveURL(/\/cloudshift-db\/replay$/)
  await expect(page.getByText('RECORDED · READ ONLY')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Play' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Recorded infrastructure topology' })).toBeVisible()
})

test('public replay supports playback, inspection, filtering, and no privileged operations', async ({ page }) => {
  await page.goto('./replay')
  await page.getByRole('button', { name: 'Play' }).click()
  await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible()
  await page.getByRole('button', { name: 'Pause' }).click()
  await page.getByRole('button', { name: 'Restart' }).click()
  await expect(page.getByText('1 / 23')).toBeVisible()

  await page.locator('.resource-node [aria-label="Inspect pg-target-parth"]').click()
  await expect(page.locator('.replay-inspector')).toContainText('PostgreSQL 16.6')
  await page.getByLabel('Filter recorded tables').fill('orders')
  await expect(page.locator('.recorded-tables tbody')).toContainText('orders')
  await page.getByLabel('Filter recorded transactions').fill('ORDER')
  await expect(page.locator('.recorded-transactions tbody tr').first()).toBeVisible()

  await expect(page.getByText('Local operator token')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Execute cutover' })).toHaveCount(0)
})

test('public layout remains usable on a phone-sized viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('./replay')
  await expect(page.getByRole('heading', { name: 'CloudShift DB migration replay' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Play' })).toBeVisible()
  await expect(page.locator('body')).toHaveCSS('min-width', '0px')
})

test('database engineering lab presents all ten verified practicals', async ({ page }) => {
  await page.goto('./database-engineering-lab')
  await expect(page.getByRole('heading', { name: 'Database Engineering Lab' })).toBeVisible()
  await expect(page.locator('.lab-grid article')).toHaveCount(10)
  await expect(page.getByText('3 physical PostgreSQL shards')).toBeVisible()
  await expect(page.getByText('9 nodes · 12 relationships')).toBeVisible()
})
