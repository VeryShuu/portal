/**
 * E2E локального админ-входа через /auth/local.
 *
 * Требует:
 *   - backend на порту 8000 (proxied через vite на /api)
 *   - LOCAL_AUTH_ENABLED=true
 *   - ADMIN_EMAIL / ADMIN_PASSWORD заданы → bootstrap admin
 */
import { test, expect } from './lib/test'

const adminEmail = process.env.E2E_ADMIN_EMAIL
const adminPassword = process.env.E2E_ADMIN_PASSWORD

const skip = !adminEmail || !adminPassword

test.describe('Admin local sign-in (/auth/local)', () => {
  test.skip(skip, 'E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD не заданы')

  test('форма локального входа отображается без кнопки SSO', async ({ page }) => {
    await page.goto('/auth/local')
    const emailInput = page.locator('input[autocomplete="email"]').first()
    await emailInput.waitFor({ timeout: 10_000 })
    // Кнопки «Войти через Keycloak» НЕ должно быть на этой странице.
    const ssoBtn = page.getByRole('button', { name: /Keycloak|SSO/i })
    await expect(ssoBtn).toHaveCount(0)
  })

  test('admin входит локально и попадает на /admin', async ({ page }) => {
    await page.goto('/auth/local')
    const emailInput = page.locator('input[autocomplete="email"]').first()
    await emailInput.waitFor({ timeout: 10_000 })
    await emailInput.fill(adminEmail!)
    await page.locator('input[type="password"]').first().fill(adminPassword!)
    await page.getByRole('button', { name: /войти|log in|sign in/i }).first().click()
    // audit-review 2026-08-22, P1: «любой URL кроме /auth/local» пропускал
    // поломки пост-логин редиректа — фиксируем админку и authed-шелл.
    await page.waitForURL((url) => !url.pathname.startsWith('/auth/'), { timeout: 15_000 })
    await expect(page).toHaveURL(/\/admin$/)
    await expect(page.locator('.app-main')).toBeVisible({ timeout: 10_000 })
  })

  test('неверный пароль показывает ошибку и оставляет на странице', async ({ page }) => {
    await page.goto('/auth/local')
    const emailInput = page.locator('input[autocomplete="email"]').first()
    await emailInput.waitFor({ timeout: 10_000 })
    await emailInput.fill('does-not-exist@portal.local')
    await page.locator('input[type="password"]').first().fill('wrong-pw')
    await page.getByRole('button', { name: /войти|log in|sign in/i }).first().click()
    // audit-review 2026-08-22, P1: «URL не изменился» пропускал сломанный
    // показ ошибки — фиксируем текст самой ошибки (401 → invalidCredentials).
    await expect(page.getByText('Неверный email или пароль').first()).toBeVisible({
      timeout: 10_000,
    })
    expect(page.url()).toContain('/auth/local')
  })

  test('?logged_out=1 показывает success-сообщение', async ({ page }) => {
    await page.goto('/auth/local?logged_out=1')
    await expect(page.getByText(/вышли|signed out/i).first()).toBeVisible({ timeout: 10_000 })
  })
})
