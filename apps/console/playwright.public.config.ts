import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests-public',
  timeout: 30_000,
  retries: 0,
  reporter: [['list']],
  webServer: {
    command: 'npm run preview:public',
    url: 'http://127.0.0.1:18083/cloudshift-db/',
    reuseExistingServer: false,
  },
  use: {
    baseURL: 'http://127.0.0.1:18083/cloudshift-db/',
    channel: 'chrome',
    headless: true,
    viewport: { width: 1440, height: 1000 },
  },
})
