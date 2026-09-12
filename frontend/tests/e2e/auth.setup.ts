/**
 * Setup-проект Playwright: единственный вход администратора для всего прогона.
 *
 * Логин по email-лимиту `/auth/local/login` — 10 попыток / 15 мин. До этого
 * каждый спек логинился админом в beforeAll → лимит исчерпывался и suites
 * падали по 429. Теперь админ входит здесь один раз, состояние сессии
 * сохраняется в storageState, а спеки создают контексты через
 * `adminContextOptions()` (см. fixtures/api.ts).
 *
 * Спеки, тестирующие сам UI логина (admin-login), продолжают
 * логиниться самостоятельно — их смысл в проверке формы.
 */
import { test as setup, expect } from './lib/test'
import { ADMIN_STATE_FILE } from './fixtures/api'

const adminEmail = process.env.E2E_ADMIN_EMAIL
const adminPassword = process.env.E2E_ADMIN_PASSWORD

setup('authenticate as admin', async ({ page }) => {
  setup.skip(!adminEmail || !adminPassword, 'E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD не заданы')

  await page.goto('/auth/local')
  const emailInput = page.locator('input[autocomplete="email"]').first()
  await emailInput.waitFor({ timeout: 10_000 })
  await emailInput.fill(adminEmail!)
  await page.locator('input[type="password"]').first().fill(adminPassword!)
  await page.getByRole('button', { name: /войти|log in|sign in/i }).first().click()
  await page.waitForURL((url) => !url.pathname.startsWith('/auth/'), { timeout: 15_000 })

  // Сессия должна быть валидной до того, как зависимые спеки начнут работу.
  const meResp = await page.evaluate(async () => {
    const resp = await fetch('/api/v1/users/me', { credentials: 'include' })
    return resp.status
  })
  expect(meResp).toBe(200)

  await page.context().storageState({ path: ADMIN_STATE_FILE })
})
