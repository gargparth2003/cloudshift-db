import { defineConfig } from '@playwright/test'

const deployedURL = process.env.CLOUDSHIFT_PUBLIC_URL

export default defineConfig({
  testDir: './tests-public',
  timeout: 30_000,
  retries: 0,
  reporter: [['list']],
  webServer: deployedURL ? undefined : {
    command: 'npm run preview:public',
    url: 'http://127.0.0.1:18083/cloudshift-db/',
    reuseExistingServer: false,
  },
  use: {
    baseURL: deployedURL ?? 'http://127.0.0.1:18083/cloudshift-db/',
    channel: 'chrome',
    headless: true,
    viewport: { width: 1440, height: 1000 },
  },
})
