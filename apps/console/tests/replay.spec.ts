import { expect, test } from '@playwright/test'

test('recorded replay exposes measured evidence and interactive event steps', async ({ page }) => {
  await page.goto('/replay')
  await expect(page.getByRole('heading', { name: 'CloudShift DB migration replay' })).toBeVisible()
  await expect(page.getByText('RECORDED · READ ONLY')).toBeVisible()
  await expect(page.getByText('424 ms')).toBeVisible()
  await expect(page.getByText('264 ms')).toBeVisible()
  await expect(page.getByText('11 / 11')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Automated cutover center' })).toBeVisible()

  await expect(page.getByText('1 / 23')).toBeVisible()
  const firstEvent = page.locator('.replay-event strong')
  await expect(firstEvent).toHaveText('MIGRATION CREATED')
  await page.getByRole('button', { name: 'Next' }).click()
  await expect(page.getByText('2 / 23')).toBeVisible()
  await expect(firstEvent).not.toHaveText('MIGRATION CREATED')
})

test('completed command center supports topology inspection and reduced motion', async ({ page }) => {
  await page.goto('/console/migration-command-center')
  await expect(page.getByRole('heading', { name: 'Live Migration Command Center' })).toBeVisible()
  await expect(page.locator('.task-strip')).toContainText('COMPLETED')
  await expect(page.locator('.task-strip')).toContainText('Route: TARGET')
  await expect(page.getByText('13 / 13')).toBeVisible()

  const reducedMotion = page.getByRole('checkbox', { name: 'Reduced motion' })
  await reducedMotion.check()
  await expect(reducedMotion).toBeChecked()

  await page.locator('.resource-node').filter({ hasText: 'pg-source-parth' }).click()
  await expect(page.locator('.inspector')).toContainText('pg-source-parth')
  await expect(page.locator('.inspector')).toContainText('AVAILABLE')
})
