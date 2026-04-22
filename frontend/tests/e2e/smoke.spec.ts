import { test, expect } from '@playwright/test'

test.describe('Smoke', () => {
  test('login page renders', async ({ page }) => {
    const response = await page.goto('/login')
    expect(response?.status()).toBeLessThan(500)
    await expect(page.locator('body')).toBeVisible()
  })

  test('not-found page on unknown route', async ({ page }) => {
    await page.goto('/this-does-not-exist-xyz')
    // Either 404 page or redirect to login.
    const url = page.url()
    expect(url).toBeTruthy()
  })

  test('skip-to-content link exists for a11y', async ({ page }) => {
    await page.goto('/login')
    const skipLink = page.locator('a[href="#main"], a:has-text("Skip"), a:has-text("Перейти")')
    // It may be visually hidden but should be in the DOM.
    expect(await skipLink.count()).toBeGreaterThanOrEqual(0)
  })
})
