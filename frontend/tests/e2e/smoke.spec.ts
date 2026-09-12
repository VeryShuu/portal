import { test, expect } from './lib/test'

import { adminContextOptions } from './fixtures/api'

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

  test('unknown route: anonymous → login redirect, authed → 404 page', async ({ page, browser }) => {
    // Аноним: guard редиректит на вход.
    const response = await page.goto('/this-does-not-exist-xyz')
    expect(response, 'navigation must yield a response').not.toBeNull()
    expect(response!.status(), 'unknown route must not 5xx').toBeLessThan(500)
    await page.waitForURL(
      (url) => url.pathname.startsWith('/login') || url.pathname.startsWith('/auth'),
      { timeout: 10_000 },
    )

    // Авторизованный (audit-review 2026-08-22, P1: раньше «URL содержит
    // неизвестный путь» пропускал отсутствие 404-страницы): NotFoundPage
    // обязан отрисоваться с кодом 404.
    const ctx = await browser.newContext(adminContextOptions())
    const authed = await ctx.newPage()
    try {
      await authed.goto('/this-does-not-exist-xyz')
      await expect(authed.getByText('Страница не найдена')).toBeVisible({ timeout: 10_000 })
    } finally {
      await ctx.close()
    }
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
