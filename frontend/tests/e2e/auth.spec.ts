import { test, expect } from '@playwright/test'

test.describe('Auth flow', () => {
  test('unauthenticated user is redirected to login or Keycloak', async ({ page }) => {
    const response = await page.goto('/', { waitUntil: 'commit' }).catch(() => null)
    if (response) {
      expect(response.status(), 'root must not 5xx').toBeLessThan(500)
    }
    // Guest на / триггерит client-side SSO-редирект через /api/v1/auth/login.
    // Когда Keycloak настроен — приземляемся на keycloak/realms; когда нет
    // (например в CI) — backend отдаёт 302 на /auth/error?reason=sso_failed.
    // Поллим page.url(): редирект через window.location.href идёт чередой
    // полностраничных навигаций, и waitForURL ловит ERR_ABORTED на прерванной
    // промежуточной навигации.
    await expect
      .poll(() => page.url(), { timeout: 15_000 })
      .toMatch(/\/auth\/(login|error|local|callback)|\/login|keycloak|realms/)
    const url = page.url()
    const matched =
      url.includes('/auth/login') ||
      url.includes('/auth/error') ||
      url.includes('/auth/local') ||
      url.includes('/login') ||
      url.includes('keycloak') ||
      url.includes('realms')
    expect(matched, `expected auth redirect, got: ${url}`).toBeTruthy()
  })

  test('auth callback page shows spinner', async ({ page }) => {
    await page.goto('/auth/callback')
    const spinner = page.locator('.n-spin')
    await expect(spinner).toBeVisible({ timeout: 5000 })
  })
})
