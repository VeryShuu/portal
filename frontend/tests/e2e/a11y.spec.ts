import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test.describe('@a11y accessibility baseline', () => {
  test('@a11y login page has no critical/serious WCAG2A violations', async ({ page }) => {
    const response = await page.goto('/login')
    expect(response, 'navigation must yield a response').not.toBeNull()
    expect(response!.status(), 'login page must return < 400').toBeLessThan(400)

    const authMarker = page.locator(
      'button:has-text("Войти"), button:has-text("Login"), a:has-text("Keycloak"), input[type="password"]'
    )
    await expect(authMarker.first()).toBeVisible({ timeout: 5000 })

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze()

    const blocking = results.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    )
    expect(
      blocking,
      `axe found ${blocking.length} critical/serious violations:\n${blocking
        .map((v) => `  - [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} nodes)`)
        .join('\n')}`
    ).toEqual([])
  })

  test('@a11y root redirect target (auth landing) has no critical/serious WCAG2A violations', async ({ page }) => {
    const response = await page.goto('/')
    expect(response, 'navigation must yield a response').not.toBeNull()
    expect(response!.status(), 'root must not 5xx').toBeLessThan(500)

    await page.waitForLoadState('domcontentloaded')

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze()

    const blocking = results.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    )
    expect(
      blocking,
      `axe found ${blocking.length} critical/serious violations on ${page.url()}:\n${blocking
        .map((v) => `  - [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length} nodes)`)
        .join('\n')}`
    ).toEqual([])
  })
})
