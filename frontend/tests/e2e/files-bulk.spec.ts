import { test, expect, type Page } from '@playwright/test'

const adminEmail = process.env.E2E_ADMIN_EMAIL
const adminPassword = process.env.E2E_ADMIN_PASSWORD

const skip = !adminEmail || !adminPassword

async function localLogin(page: Page, email: string, password: string) {
  await page.goto('/login')
  const emailInput = page.locator('input[type="email"], input[name="email"]').first()
  await emailInput.waitFor({ timeout: 10_000 })
  await emailInput.fill(email)
  await page.locator('input[type="password"]').first().fill(password)
  await page.getByRole('button', { name: /войти|log in|sign in/i }).first().click()
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15_000 })
}

async function getCsrfToken(page: Page): Promise<string> {
  return page.evaluate(async () => {
    const resp = await fetch('/api/v1/auth/csrf-token', { credentials: 'include' })
    const json = await resp.json().catch(() => ({}))
    return json.csrf_token || ''
  })
}

async function apiJson(
  page: Page,
  method: string,
  path: string,
  body?: unknown,
): Promise<{ status: number; data: unknown }> {
  const csrf = await getCsrfToken(page)
  return page.evaluate(
    async ({ method, path, body, csrf }) => {
      const resp = await fetch(`/api/v1${path}`, {
        method,
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrf,
        },
        body: body != null ? JSON.stringify(body) : undefined,
      })
      let data: unknown
      try {
        data = await resp.json()
      } catch {
        data = null
      }
      return { status: resp.status, data }
    },
    { method, path, body, csrf },
  )
}

const RANDOM_UUID = '00000000-0000-4000-8000-000000000000'

test.describe('Files bulk operations API', () => {
  test.skip(skip, 'E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD не заданы')

  test.beforeEach(async ({ page }) => {
    await localLogin(page, adminEmail!, adminPassword!)
  })

  test('bulk-delete с пустым списком отдаёт 422', async ({ page }) => {
    const r = await apiJson(page, 'POST', `/files/folders/${RANDOM_UUID}/bulk-delete`, {
      filenames: [],
    })
    expect(r.status).toBe(422)
  })

  test('bulk-delete с >100 именами отдаёт 422', async ({ page }) => {
    const filenames = Array.from({ length: 101 }, (_, i) => `f${i}.txt`)
    const r = await apiJson(page, 'POST', `/files/folders/${RANDOM_UUID}/bulk-delete`, {
      filenames,
    })
    expect(r.status).toBe(422)
  })

  test('bulk-move в ту же папку отдаёт 422 same_folder', async ({ page }) => {
    const r = await apiJson(page, 'POST', `/files/folders/${RANDOM_UUID}/bulk-move`, {
      filenames: ['a.txt'],
      target_folder_id: RANDOM_UUID,
    })
    expect(r.status).toBe(422)
    expect(JSON.stringify(r.data)).toContain('same_folder')
  })

  test('bulk-delete без CSRF отдаёт 403', async ({ page }) => {
    const status = await page.evaluate(async (uuid) => {
      const resp = await fetch(`/api/v1/files/folders/${uuid}/bulk-delete`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filenames: ['a.txt'] }),
      })
      return resp.status
    }, RANDOM_UUID)
    expect([401, 403]).toContain(status)
  })
})
