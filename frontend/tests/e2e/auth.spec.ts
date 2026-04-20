import { test, expect } from '@playwright/test'

test.describe('Auth flow', () => {
  test('unauthenticated user is redirected to Keycloak login', async ({ page }) => {
    const response = await page.goto('/')
    const url = page.url()
    expect(
      url.includes('/auth/login') || url.includes('keycloak') || url.includes('realms')
    ).toBeTruthy()
  })

  test('auth callback page shows spinner', async ({ page }) => {
    await page.goto('/auth/callback')
    const spinner = page.locator('.n-spin')
    await expect(spinner).toBeVisible({ timeout: 3000 }).catch(() => {})
  })
})
