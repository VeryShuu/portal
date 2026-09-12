/**
 * E2E Files bulk API — контракты валидации bulk-операций.
 *
 * Требует:
 *   - backend с включённым модулем nextcloud (ModuleCheck иначе отдаёт 503
 *     ДО Pydantic-валидации — CI сеет /data/settings/modules.json)
 *   - admin-сессию из setup-проекта (auth.setup.ts)
 *
 * NC-сервер не нужен: все проверки срабатывают до обращения к Nextcloud
 * (валидация тела → 422, same_folder → 422 до lookup папок, CSRF → 403).
 */
import { test, expect, type Browser, type Page } from './lib/test'
import { apiRequest, newAdminPage } from './fixtures/api'

const adminEmail = process.env.E2E_ADMIN_EMAIL
const adminPassword = process.env.E2E_ADMIN_PASSWORD

const skip = !adminEmail || !adminPassword

const RANDOM_UUID = '00000000-0000-4000-8000-000000000000'

test.describe('Files bulk operations API', () => {
  test.describe.configure({ mode: 'serial' })
  test.skip(skip, 'E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD не заданы')

  let page: Page

  test.beforeAll(async ({ browser }: { browser: Browser }) => {
    page = await newAdminPage(browser)
  })

  test.afterAll(async () => {
    await page?.context().close()
  })

  test('bulk-delete с пустым списком отдаёт 422', async () => {
    const r = await apiRequest(page, 'POST', `/files/folders/${RANDOM_UUID}/bulk-delete`, {
      filenames: [],
    })
    expect(r.status).toBe(422)
  })

  test('bulk-delete с >100 именами отдаёт 422', async () => {
    const filenames = Array.from({ length: 101 }, (_, i) => `f${i}.txt`)
    const r = await apiRequest(page, 'POST', `/files/folders/${RANDOM_UUID}/bulk-delete`, {
      filenames,
    })
    expect(r.status).toBe(422)
  })

  test('bulk-move в ту же папку отдаёт 422 same_folder', async () => {
    const r = await apiRequest(page, 'POST', `/files/folders/${RANDOM_UUID}/bulk-move`, {
      filenames: ['a.txt'],
      target_folder_id: RANDOM_UUID,
    })
    expect(r.status).toBe(422)
    expect(JSON.stringify(r.data)).toContain('same_folder')
  })

  test('bulk-delete без CSRF отдаёт 403', async () => {
    // audit-review follow-up, P1: [401, 403] пропускало сломанный CSRF-механизм
    // (401 = упали раньше проверки токена). Сессия валидна (storageState),
    // Origin не отправлен → ровно CSRF-отказ.
    const status = await page.evaluate(async (uuid) => {
      const resp = await fetch(`/api/v1/files/folders/${uuid}/bulk-delete`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filenames: ['a.txt'] }),
      })
      return resp.status
    }, RANDOM_UUID)
    expect(status).toBe(403)
  })
})
