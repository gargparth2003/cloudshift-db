import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.CLOUDSHIFT_CONSOLE_URL ?? 'http://127.0.0.1:18080',
    channel: 'chrome',
    headless: true,
    viewport: { width: 1600, height: 1200 },
    trace: 'retain-on-failure',
  },
})
