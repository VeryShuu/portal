/**
 * Smoke security: проверка наличия security-заголовков на ответах backend через прокси.
 */
import { test, expect } from '@playwright/test'

test('backend returns security headers via /health', async ({ request }) => {
  // /health не имеет /api префикса; vite dev-сервер проксирует /health на backend.
  // Увеличенный timeout: первый проксируемый запрос ждёт «прогрева» dev-сервера vite.
  const r = await request.get('/health', { timeout: 30_000 })
  expect(r.status()).toBe(200)
  const h = r.headers()
  expect(h['x-content-type-options']).toBe('nosniff')
  expect(h['x-frame-options']).toBe('DENY')
})
