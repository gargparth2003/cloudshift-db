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

test('recruiter can open the three-mode platform and preload an engineering scenario', async ({ page }) => {
  await page.goto('./platform/')
  await expect(page.getByRole('heading', { name: 'Plan, simulate, and inspect a cloud database migration' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Mode A/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Mode B/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Mode C/ })).toBeVisible()
  await page.getByRole('button', { name: /Bandwidth-constrained migration/ }).click()
  await expect(page.getByText('constrained', { exact: true })).toBeVisible()
  await expect(page.getByText('800 GB · 48 tables')).toBeVisible()
})

test('migration wizard persists a provider plan and exports structured JSON', async ({ page }) => {
  await page.goto('./migration-studio/planner/')
  await page.getByRole('button', { name: /Destination cloud/ }).click()
  await page.getByLabel('Destination provider').selectOption('GCP')
  await page.getByRole('button', { name: /Destination region/ }).click()
  await expect(page.getByLabel('Destination region')).toHaveValue('asia-south1')
  await page.getByRole('button', { name: /Database configuration/ }).click()
  await page.getByLabel('Database size (GB)').fill('100')
  await page.getByLabel('Transactions/second').fill('150')
  await page.getByRole('button', { name: /Review and generate plan/ }).click()
  await expect(page.locator('.review-plan pre')).toContainText('cloudshift-migration-plan')
  await expect(page.locator('.review-plan pre')).toContainText('asia-south1')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download migration plan JSON' }).click()
  await expect((await download).suggestedFilename()).toMatch(/\.json$/)
})

test('deterministic sandbox builds backlog, blocks invalid cutover, recovers, validates, and switches route', async ({ page }) => {
  await page.goto('./platform/')
  await page.evaluate(() => localStorage.setItem('cloudshift-v1.1-migration-plan', JSON.stringify({
    databaseSizeGB: 0.0001, transactionsPerSecond: 0, targetApplyMBps: 50,
  })))
  await page.goto('./migration-studio/sandbox/')
  await page.getByRole('button', { name: 'Start', exact: true }).click()
  await page.getByRole('button', { name: 'Interrupt network' }).click()
  await expect(page.getByText('NETWORK PARTITION', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Execute modeled cutover' }).click()
  await expect(page.getByText('CUTOVER BLOCKED')).toBeVisible()
  await page.getByRole('button', { name: 'Restore network' }).click()
  await page.waitForTimeout(1200)
  await page.getByRole('button', { name: 'Inject validation mismatch' }).click()
  await page.getByRole('button', { name: 'Run validation' }).click()
  await expect(page.getByText('VALIDATION FAILED')).toBeVisible()
  await page.getByRole('button', { name: 'Repair mismatch' }).click()
  await page.getByRole('button', { name: 'Run validation' }).click()
  await page.getByRole('button', { name: 'Execute modeled cutover' }).click()
  await expect(page.locator('.simulation-metrics')).toContainText('TARGET')
  await expect(page.getByText('CUTOVER COMPLETED')).toBeVisible()
})

test('network playground detects overlap and explains modeled connectivity', async ({ page }) => {
  await page.goto('./infrastructure/network/')
  await page.getByLabel('Private database subnet B').fill('10.42.20.128/25')
  await expect(page.getByText('Subnet overlap')).toBeVisible()
  const overlap = page.locator('.assessment-table details').filter({ hasText: 'Subnet overlap' })
  await expect(overlap).toContainText('FAIL')
  await expect(page.getByText('Application → database')).toBeVisible()
})

test('FinOps formulas and AWS Terraform output respond to planning inputs', async ({ page }) => {
  await page.goto('./optimization/cost/')
  await page.getByLabel('Database instance / hour').fill('1')
  await page.getByLabel('Application hosting / hour').fill('0.1')
  await expect(page.locator('.cost-result>strong')).not.toContainText('$0.00')
  await page.goto('./infrastructure/terraform/')
  await page.getByRole('button', { name: 'main.tf', exact: true }).click()
  await expect(page.locator('.code-workspace pre')).toContainText('publicly_accessible = false')
  await expect(page.locator('.code-workspace pre')).toContainText('storage_encrypted = true')
  await expect(page.getByText('terraform apply can create billable resources')).toBeVisible()
})

test('static route artifacts serve successful direct responses and refresh', async ({ page }) => {
  for (const route of ['platform/', 'migration-studio/planner/', 'infrastructure/builder/', 'infrastructure/terraform/', 'operations/reliability/', 'optimization/feasibility/']) {
    const response = await page.goto(`./${route}`)
    expect(response?.status()).toBeLessThan(400)
    await page.reload()
    await expect(page.getByRole('link', { name: /CloudShift DB Migration & Operations Platform/ })).toBeVisible()
  }
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
  await page.goto('./platform/')
  await expect(page.getByRole('heading', { name: 'Plan, simulate, and inspect a cloud database migration' })).toBeVisible()
  await expect(page.locator('body')).toHaveCSS('min-width', '0px')
})

test('database engineering lab presents all ten verified practicals', async ({ page }) => {
  await page.goto('./database-engineering-lab')
  await expect(page.getByRole('heading', { name: 'Database Engineering Lab' })).toBeVisible()
  await expect(page.locator('.lab-grid article')).toHaveCount(10)
  await expect(page.getByText('3 physical PostgreSQL shards')).toBeVisible()
  await expect(page.getByText('9 nodes · 12 relationships')).toBeVisible()
})
