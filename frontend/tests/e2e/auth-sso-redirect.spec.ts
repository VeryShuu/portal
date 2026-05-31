/**
 * E2E auto-SSO редиректа гостя.
 *
 * /api/v1/auth/login замоканы через page.route, чтобы тест не зависел
 * от реального Keycloak — стаб возвращает 302 на /auth/error?reason=sso_failed,
 * имитируя цикл «гость → SSO → ошибка».
 */
import { test, expect } from '@playwright/test'

test.describe('Auto-SSO redirect for guests', () => {
  test('гость на / → редирект на /api/v1/auth/login c redirect-параметром', async ({ page }) => {
    let capturedUrl = ''
    await page.route('**/api/v1/auth/login*', async (route) => {
      capturedUrl = route.request().url()
      await route.fulfill({
        status: 302,
        headers: { location: '/auth/error?reason=sso_failed' },
      })
    })
    await page.goto('/', { waitUntil: 'commit' }).catch(() => {})
    // Поллим page.url() вместо waitForURL: гость проходит через несколько
    // полностраничных навигаций (window.location.href), и waitForURL цепляется
    // за промежуточную навигацию на «/», которую прерывает редирект → ERR_ABORTED.
    await expect.poll(() => page.url(), { timeout: 15_000 }).toMatch(/\/auth\/error/)
    expect(capturedUrl).toContain('/api/v1/auth/login')
  })

  test('гость на /kb/articles/123 → redirect= сохраняется', async ({ page }) => {
    let capturedUrl = ''
    await page.route('**/api/v1/auth/login*', async (route) => {
      capturedUrl = route.request().url()
      await route.fulfill({
        status: 302,
        headers: { location: '/auth/error?reason=sso_failed' },
      })
    })
    await page.goto('/kb/articles/123', { waitUntil: 'commit' }).catch(() => {})
    await expect.poll(() => page.url(), { timeout: 15_000 }).toMatch(/\/auth\/error/)
    expect(capturedUrl).toContain('redirect=')
    expect(decodeURIComponent(capturedUrl)).toContain('/kb/articles/123')
  })

  test('страница /auth/error?reason=sso_failed показывает кнопку «Войти снова»', async ({ page }) => {
    await page.goto('/auth/error?reason=sso_failed')
    await expect(page.getByRole('button', { name: /войти снова|sign in again/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /администратор|administrator/i })).toBeVisible()
  })

  test('/auth/error?reason=logged_out показывает success-сообщение', async ({ page }) => {
    await page.goto('/auth/error?reason=logged_out')
    await expect(page.getByText(/вышли|signed out/i).first()).toBeVisible({ timeout: 10_000 })
  })

  test('loop scenario: 2 редиректа за 30s → /auth/error?reason=loop_detected', async ({ page, context }) => {
    // Не успеваем дойти до Keycloak — отдадим 200 пустую страницу, чтобы не редиректить дальше
    await page.route('**/api/v1/auth/login*', async (route) => {
      await route.fulfill({ status: 200, body: '' })
    })
    // Симулируем 2 предыдущие попытки в sessionStorage
    await context.addInitScript(() => {
      const now = Date.now()
      sessionStorage.setItem('sso_attempts', JSON.stringify([now - 1000, now - 500]))
    })
    await page.goto('/', { waitUntil: 'commit' }).catch(() => {})
    await expect.poll(() => page.url(), { timeout: 15_000 }).toMatch(/\/auth\/error\?reason=loop_detected/)
  })
})
