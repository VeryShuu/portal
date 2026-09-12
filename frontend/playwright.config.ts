import { defineConfig, devices } from '@playwright/test'

const port = process.env.E2E_PORT ?? '5173'
const baseURL = process.env.E2E_BASE_URL ?? `http://localhost:${port}`
const e2eMode = (process.env.E2E_MODE ?? (process.env.CI ? 'preview' : 'dev')).toLowerCase()
const missingCiCredentials =
  process.env.CI && (!process.env.E2E_ADMIN_EMAIL || !process.env.E2E_ADMIN_PASSWORD)

if (missingCiCredentials) {
  throw new Error(
    'CI Playwright requires E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD; authenticated suites must not be skipped',
  )
}

// strictPort обязателен: без него занятый порт молча инкрементируется (5173→5174),
// а Playwright продолжает ждать baseURL на 5173 — и может прицепиться к vite
// ПАРАЛЛЕЛЬНОГО CI-run'а (аудит тестирования 2026-08-21, P0.4).
const webServerCommand =
  e2eMode === 'preview'
    ? `npm run build && npx vite preview --port ${port} --strictPort`
    : `npm run dev -- --port ${port} --strictPort`

// Learn-контур (ADR-051): второй web-server (отдельная сборка learn) + проект
// learn. Включается E2E_LEARN=1 (CI); локально по умолчанию не гоняется.
const learnPort = process.env.LEARN_PORT ?? '4174'
const learnEnabled = !!process.env.E2E_LEARN

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 4 : undefined,
  reporter: process.env.CI
    ? [
        ['github'],
        ['html', { open: 'never' }],
        // includeRetries: ретраи попадают в junit как rerunError/flakyError —
        // их читает flaky-бюджет (scripts/parse-e2e-flaky.mjs). Без флага
        // гейт ложнозелёный (audit-review follow-up, P1).
        ['junit', { outputFile: 'playwright-report/results.xml', includeRetries: true }],
      ]
    : 'list',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL,
    extraHTTPHeaders: process.env.E2E_REAL_IP
      ? { 'X-Real-IP': process.env.E2E_REAL_IP }
      : undefined,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
    viewport: { width: 1280, height: 800 },
    locale: 'ru-RU',
  },
  projects: [
    // Единственный admin-логин прогона: сессия сохраняется в storageState
    // (ADMIN_STATE_FILE), остальные проекты зависят от него. Спеки UI логина
    // (admin-login, local-login) используют собственные свежие контексты.
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: 'chromium',
      dependencies: ['setup'],
      use: { ...devices['Desktop Chrome'] },
      // learn-спек живёт только в проекте learn (свой baseURL learn-контура)
      testIgnore: /learn-.*\.spec\.ts/,
    },
    {
      name: 'firefox',
      dependencies: ['setup'],
      use: { ...devices['Desktop Firefox'] },
      testIgnore: /.*\.mobile\.spec\.ts|learn-.*\.spec\.ts/,
    },
    {
      name: 'webkit',
      dependencies: ['setup'],
      use: { ...devices['Desktop Safari'] },
      testIgnore: /.*\.mobile\.spec\.ts|learn-.*\.spec\.ts/,
    },
    {
      name: 'mobile',
      dependencies: ['setup'],
      use: { ...devices['iPhone 13'] },
      testMatch: /.*\.mobile\.spec\.ts/,
    },
    ...(learnEnabled
      ? [
          {
            name: 'learn',
            dependencies: ['setup'],
            testMatch: /learn-.*\.spec\.ts/,
            use: { ...devices['Desktop Chrome'], baseURL: `http://localhost:${learnPort}` },
          },
        ]
      : []),
  ],
  webServer: process.env.E2E_NO_WEBSERVER
    ? undefined
    : [
        {
          command: webServerCommand,
          url: baseURL,
          reuseExistingServer: !process.env.CI,
          timeout: e2eMode === 'preview' ? 180_000 : 60_000,
        },
        ...(learnEnabled
          ? [
              {
                command: `npm run build:learn && npx vite preview --config vite.config.learn.ts --port ${learnPort} --strictPort`,
                url: `http://localhost:${learnPort}`,
                reuseExistingServer: !process.env.CI,
                timeout: 180_000,
              },
            ]
          : []),
      ],
})
