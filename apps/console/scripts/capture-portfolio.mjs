import { mkdir, rename, readdir } from 'node:fs/promises'
import { chromium } from '@playwright/test'
import path from 'node:path'

const baseURL = process.env.CLOUDSHIFT_CONSOLE_URL ?? 'http://127.0.0.1:18080'
const output = path.resolve('../../artifacts/screenshots')
const videoOutput = path.resolve('../../artifacts/video')
await mkdir(output, { recursive: true })
await mkdir(videoOutput, { recursive: true })

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 }, deviceScaleFactor: 1 })

await page.goto(`${baseURL}/`)
await page.screenshot({ path: path.join(output, 'portfolio-landing.png'), fullPage: true })

await page.goto(`${baseURL}/console/migration-command-center`)
await page.locator('.resource-node [aria-label="Inspect pg-source-parth"]').click()
await page.screenshot({ path: path.join(output, 'live-command-center.png'), fullPage: true })
await page.locator('.workspace-grid').screenshot({ path: path.join(output, 'live-resource-inspection.png') })
await page.locator('.table-panel').screenshot({ path: path.join(output, 'table-migration-tracker.png') })
await page.locator('.transaction-panel').screenshot({ path: path.join(output, 'transaction-inspector.png') })

await page.goto(`${baseURL}/replay`)
await page.screenshot({ path: path.join(output, 'public-recorded-replay.png'), fullPage: true })
await page.getByLabel('Replay event').fill('4')
await page.locator('.replay-topology-grid').screenshot({ path: path.join(output, 'source-target-transfer.png') })
await page.locator('.replay-grid').first().screenshot({ path: path.join(output, 'controlled-cutover.png') })
await page.locator('#performance').screenshot({ path: path.join(output, 'performance-observations.png') })
await page.locator('#report').screenshot({ path: path.join(output, 'validation-and-recovery.png') })

await page.goto(`${baseURL}/database-engineering-lab`)
await page.screenshot({ path: path.join(output, 'database-engineering-lab.png'), fullPage: true })
await page.close()

const videoContext = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: videoOutput, size: { width: 1280, height: 720 } },
})
const videoPage = await videoContext.newPage()
await videoPage.goto(`${baseURL}/replay`)
await videoPage.locator('#topology').scrollIntoViewIfNeeded()
await videoPage.getByLabel('Playback speed').selectOption('2')
await videoPage.getByRole('button', { name: 'Play' }).click()
await videoPage.waitForTimeout(14_500)
await videoContext.close()
await browser.close()

const videos = (await readdir(videoOutput)).filter(name => name.endsWith('.webm'))
if (videos.length) await rename(path.join(videoOutput, videos.at(-1)), path.join(videoOutput, 'migration-replay.webm'))
console.log(`Captured portfolio evidence in ${output}`)
