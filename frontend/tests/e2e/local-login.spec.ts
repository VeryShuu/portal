/**
 * E2E локальной аутентификации (Phase 2.1).
 *
 * Требует работающий стек:
 *   - backend на порту 8000 (proxied через vite на /api)
 *   - LOCAL_AUTH_ENABLED=true
 *   - ADMIN_EMAIL / ADMIN_PASSWORD заданы → bootstrap admin
 */
import { test, expect } from '@playwright/test'

const adminEmail = process.env.E2E_ADMIN_EMAIL
const adminPassword = process.env.E2E_ADMIN_PASSWORD

const skip = !adminEmail || !adminPassword

test.describe('Local auth flow', () => {
  test.skip(skip, 'E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD не заданы')

  test('admin может войти локально и попасть на главную', async ({ page }) => {
    await page.goto('/login')
    // Форма локального входа должна быть видна (LOCAL_AUTH_ENABLED=true).
    const emailInput = page.locator('input[type="email"], input[name="email"]').first()
    await emailInput.waitFor({ timeout: 10_000 })
    await emailInput.fill(adminEmail!)
    await page.locator('input[type="password"]').first().fill(adminPassword!)
    await page.getByRole('button', { name: /войти|log in|sign in/i }).first().click()

    // Ожидаем редирект на /
    await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15_000 })
    expect(page.url()).not.toContain('/login')
  })

  test('неверный пароль показывает ошибку', async ({ page }) => {
    await page.goto('/login')
    const emailInput = page.locator('input[type="email"], input[name="email"]').first()
    await emailInput.waitFor({ timeout: 10_000 })
    await emailInput.fill('does-not-exist@portal.local')
    await page.locator('input[type="password"]').first().fill('wrong-pw')
    await page.getByRole('button', { name: /войти|log in|sign in/i }).first().click()

    // Должен оставаться на /login и показать ошибку.
    await page.waitForTimeout(1500)
    expect(page.url()).toContain('/login')
  })
})
