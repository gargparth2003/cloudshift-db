import { mkdir, readdir, rename } from 'node:fs/promises'
import { chromium } from '@playwright/test'
import path from 'node:path'

const baseURL = (process.env.CLOUDSHIFT_PUBLIC_URL ?? 'http://127.0.0.1:18083/cloudshift-db').replace(/\/$/, '')
const screenshotOutput = path.resolve('../../artifacts/screenshots')
const videoOutput = path.resolve('../../artifacts/video')
await mkdir(screenshotOutput, { recursive: true })
await mkdir(videoOutput, { recursive: true })

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const context = await browser.newContext({ viewport: { width: 1600, height: 1200 }, deviceScaleFactor: 1 })
const page = await context.newPage()
await page.route('**/api/**', route => route.abort())
await page.route('**/workload-api/**', route => route.abort())

async function capture(route, name) {
  await page.goto(`${baseURL}${route}`)
  await page.screenshot({ path: path.join(screenshotOutput, name), fullPage: true })
}

await capture('/platform/', 'v1.1-platform-overview.png')
await capture('/migration-studio/planner/', 'v1.1-migration-planner.png')

await page.evaluate(() => localStorage.setItem('cloudshift-v1.1-migration-plan', JSON.stringify({
  databaseSizeGB: 0.0001,
  transactionsPerSecond: 20_000,
  targetApplyMBps: 1,
})))
await page.goto(`${baseURL}/migration-studio/sandbox/`)
await page.getByRole('button', { name: 'Start', exact: true }).click()
await page.getByRole('button', { name: 'Interrupt network' }).click()
await page.getByRole('button', { name: 'Execute modeled cutover' }).click()
await page.screenshot({ path: path.join(screenshotOutput, 'v1.1-sandbox-failure-guard.png') })

await capture('/infrastructure/builder/', 'v1.1-architecture-builder.png')
await capture('/infrastructure/network/', 'v1.1-network-security.png')
await capture('/optimization/cost/', 'v1.1-finops-estimator.png')
await capture('/infrastructure/terraform/', 'v1.1-terraform-generator.png')
await context.close()

const existingVideos = new Set((await readdir(videoOutput)).filter(name => name.endsWith('.webm')))
const videoContext = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: videoOutput, size: { width: 1440, height: 900 } },
})
const videoPage = await videoContext.newPage()
await videoPage.route('**/api/**', route => route.abort())
await videoPage.goto(`${baseURL}/platform/`)
await videoPage.getByRole('button', { name: /Bandwidth-constrained migration/ }).click()
await videoPage.waitForTimeout(1_000)
await videoPage.goto(`${baseURL}/migration-studio/sandbox/`)
await videoPage.getByRole('button', { name: 'Start', exact: true }).click()
await videoPage.waitForTimeout(1_500)
await videoPage.getByRole('button', { name: 'Interrupt network' }).click()
await videoPage.waitForTimeout(1_500)
await videoPage.getByRole('button', { name: 'Execute modeled cutover' }).click()
await videoPage.waitForTimeout(1_500)
await videoPage.getByRole('button', { name: 'Restore network' }).click()
await videoPage.waitForTimeout(1_500)
await videoPage.goto(`${baseURL}/infrastructure/builder/`)
await videoPage.waitForTimeout(1_500)
await videoPage.goto(`${baseURL}/optimization/cost/`)
await videoPage.waitForTimeout(1_500)
await videoContext.close()
await browser.close()

const createdVideo = (await readdir(videoOutput)).find(name => name.endsWith('.webm') && !existingVideos.has(name))
if (createdVideo) await rename(path.join(videoOutput, createdVideo), path.join(videoOutput, 'v1.1-cloud-platform.webm'))
console.log(`Captured CloudShift DB v1.1 evidence in ${screenshotOutput}`)
