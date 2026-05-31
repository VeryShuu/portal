import { test, expect } from '@playwright/test'

test.describe('Smoke', () => {
  test('login page renders with successful HTTP status', async ({ page }) => {
    const response = await page.goto('/login')
    expect(response, 'navigation must yield a response').not.toBeNull()
    expect(response!.status(), 'login page must return < 400').toBeLessThan(400)
    await expect(page.locator('body')).toBeVisible()
    const authMarker = page.locator(
      'button:has-text("Войти"), button:has-text("Login"), a:has-text("Keycloak"), input[type="password"]'
    )
    await expect(authMarker.first()).toBeVisible({ timeout: 5000 })
  })

  test('unknown route resolves (404 page or login redirect)', async ({ page }) => {
    const response = await page.goto('/this-does-not-exist-xyz')
    expect(response, 'navigation must yield a response').not.toBeNull()
    expect(response!.status(), 'unknown route must not 5xx').toBeLessThan(500)
    const url = page.url()
    expect(
      url.includes('/login') ||
        url.includes('/auth') ||
        url.includes('/404') ||
        url.includes('this-does-not-exist-xyz'),
      `unexpected URL after navigation: ${url}`
    ).toBeTruthy()
  })

  test('public auth page exposes a main landmark for a11y', async ({ page }) => {
    // После перехода на SSO-only вход (commit «Переделываем авторизацию»)
    // skip-to-content ссылка живёт только в authed-shell (AppLayout, #main-content).
    // Для публичной точки входа базовый a11y-контракт — наличие <main> landmark
    // на странице локального логина.
    await page.goto('/auth/local')
    await expect(page.locator('main')).toHaveCount(1)
  })
})
