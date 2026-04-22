/**
 * Smoke security: проверка наличия security-заголовков на ответах backend через прокси.
 */
import { test, expect } from '@playwright/test'

test('backend returns security headers via /health', async ({ request }) => {
  const r = await request.get('/api/v1/../health').catch(() => null)
  // /health не имеет /api префикса; ходим напрямую через baseURL/health.
  const r2 = r ?? (await request.get('/health'))
  expect(r2.status()).toBe(200)
  const h = r2.headers()
  expect(h['x-content-type-options']).toBe('nosniff')
  expect(h['x-frame-options']).toBe('DENY')
})
