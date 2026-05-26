import { test, expect } from '@playwright/test'

test.describe('Auth flow', () => {
  test('unauthenticated user is redirected to login or Keycloak', async ({ page }) => {
    const response = await page.goto('/')
    expect(response, 'navigation must yield a response').not.toBeNull()
    expect(response!.status(), 'root must not 5xx').toBeLessThan(500)
    const url = page.url()
    const matched =
      url.includes('/auth/login') ||
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
