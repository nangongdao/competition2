import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E 配置。
 *
 * 关键用户流程测试（TD-7 补强）：验证前端关键交互链路。
 * 测试通过 page.route() 拦截 WebSocket 与 API 请求，用桩数据驱动，
 * 无需真实后端/ASR/NMT（避免外部 API 依赖），可本地与 CI 稳定运行。
 *
 * 运行：
 *   cd frontend
 *   npx playwright install chromium   # 首次
 *   npm run e2e                       # 构建 + 跑 E2E
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['html', { open: 'never' }], ['list']] : 'list',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npx vite preview --port 4173 --host 127.0.0.1',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: true,
    timeout: 30_000,
  },
})
