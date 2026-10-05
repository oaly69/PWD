// 端到端测试：启动模拟模型服务（9001）与 PWD（8080，使用临时数据目录和已构建的前端），在 Chromium 中走完整流程。
// 本地运行：先构建前端（cd frontend && npm run build），再在 e2e 目录执行 npm ci && npx playwright install chromium && npm test
import { defineConfig } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const dataDir = process.env.PWD_E2E_DATA || mkdtempSync(path.join(tmpdir(), 'pwd-e2e-'))
const python = process.env.PYTHON || 'python'

export default defineConfig({
  testDir: './tests',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://127.0.0.1:8080',
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  webServer: [
    {
      command: `${python} -m uvicorn mock_server:app --port 9001`,
      url: 'http://127.0.0.1:9001/v1/models',
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `${python} -m uvicorn app.main:app --port 8080`,
      cwd: '../backend',
      url: 'http://127.0.0.1:8080/api/health',
      env: { PWD_DATA_DIR: dataDir, PWD_STATIC_DIR: path.resolve('../frontend/dist') },
      reuseExistingServer: false,
    },
  ],
})
