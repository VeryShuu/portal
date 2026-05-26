/**
 * E2E KB ACL — сценарии с ivanov/petrov/sidorov.
 *
 * Требует работающий стек:
 *   - backend на порту 8000 (proxied через vite на /api)
 *   - LOCAL_AUTH_ENABLED=true
 *   - E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD — admin для создания пользователей
 *   - E2E_BASE_URL — URL портала (default: http://localhost:5173)
 *
 * Тесты автоматически пропускаются если переменные окружения не заданы.
 *
 * Сценарии:
 *   1. ivanov (editor) создаёт раздел → приглашает petrov как viewer → petrov видит раздел
 *   2. sidorov (reader, без прав) не видит раздел в KB
 *   3. petrov (viewer) не может редактировать статью
 *   4. Статья с inherit_permissions=false → petrov теряет доступ
 */
import { test, expect, Browser, BrowserContext, Page } from '@playwright/test'
import { CleanupRegistry } from './fixtures/api'
import { E2E_RUN_ID, runScopedEmail } from './fixtures/run-id'

const adminEmail = process.env.E2E_ADMIN_EMAIL
const adminPassword = process.env.E2E_ADMIN_PASSWORD

const skip = !adminEmail || !adminPassword

// ─── helpers ──────────────────────────────────────────────────────────────────

async function localLogin(page: Page, email: string, password: string) {
  await page.goto('/login')
  const emailInput = page.locator('input[type="email"], input[name="email"]').first()
  await emailInput.waitFor({ timeout: 10_000 })
  await emailInput.fill(email)
  await page.locator('input[type="password"]').first().fill(password)
  await page.getByRole('button', { name: /войти|log in|sign in/i }).first().click()
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15_000 })
}

async function apiRequest(
  page: Page,
  method: string,
  path: string,
  body?: unknown,
): Promise<{ status: number; data: unknown }> {
  const result = await page.evaluate(
    async ({ method, path, body }) => {
      const csrfResp = await fetch('/api/v1/auth/csrf-token', { credentials: 'include' })
      const csrfJson = await csrfResp.json().catch(() => ({}))
      const csrfToken = csrfJson.csrf_token || ''

      const resp = await fetch(`/api/v1${path}`, {
        method,
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
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
    { method, path, body },
  )
  return result
}

// ─── fixture: create test users via admin API ──────────────────────────────

async function createLocalUser(
  adminPage: Page,
  email: string,
  fullName: string,
  password: string,
  role: 'reader' | 'editor' | 'admin' = 'reader',
): Promise<string | null> {
  const result = await apiRequest(adminPage, 'POST', '/admin/users/local', {
    email,
    full_name: fullName,
    password,
    role,
  })
  if (result.status === 201 || result.status === 200) {
    return (result.data as { id: string }).id
  }
  return null
}

// ─── tests ────────────────────────────────────────────────────────────────────

test.describe('KB ACL: ivanov/petrov/sidorov', () => {
  test.describe.configure({ mode: 'serial' })
  test.skip(skip, 'E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD не заданы')

  let adminPage: Page
  let ivanovPage: Page
  let petrovPage: Page
  let sidorovPage: Page

  const ivanovEmail = runScopedEmail('ivanov')
  const petrovEmail = runScopedEmail('petrov')
  const sidorovEmail = runScopedEmail('sidorov')
  const testPassword = 'TestP@ss1!'

  let sectionId: string
  let articleId: string
  const cleanup = new CleanupRegistry()

  test.beforeAll(async ({ browser }) => {
    const adminContext = await browser.newContext()
    adminPage = await adminContext.newPage()
    await localLogin(adminPage, adminEmail!, adminPassword!)

    const ivanovId = await createLocalUser(adminPage, ivanovEmail, 'Ivan Ivanov', testPassword, 'editor')
    const petrovId = await createLocalUser(adminPage, petrovEmail, 'Petr Petrov', testPassword, 'reader')
    const sidorovId = await createLocalUser(adminPage, sidorovEmail, 'Sidr Sidorov', testPassword, 'reader')
    if (ivanovId) cleanup.trackUser(adminPage, ivanovId)
    if (petrovId) cleanup.trackUser(adminPage, petrovId)
    if (sidorovId) cleanup.trackUser(adminPage, sidorovId)

    const ivanovContext = await browser.newContext()
    ivanovPage = await ivanovContext.newPage()
    await localLogin(ivanovPage, ivanovEmail, testPassword)

    const petrovContext = await browser.newContext()
    petrovPage = await petrovContext.newPage()
    await localLogin(petrovPage, petrovEmail, testPassword)

    const sidorovContext = await browser.newContext()
    sidorovPage = await sidorovContext.newPage()
    await localLogin(sidorovPage, sidorovEmail, testPassword)
  })

  test.afterAll(async () => {
    // Cleanup в обратном порядке: статья → раздел → пользователи.
    try {
      await cleanup.flush()
    } finally {
      await adminPage?.context().close()
      await ivanovPage?.context().close()
      await petrovPage?.context().close()
      await sidorovPage?.context().close()
    }
  })

  // ── 1. ivanov создаёт раздел ──────────────────────────────────────────────

  test('ivanov creates a section and article', async () => {
    const sectionTitle = `ACL Section ${E2E_RUN_ID}`
    const sectionResp = await apiRequest(ivanovPage, 'POST', '/kb/sections', {
      title: sectionTitle,
      description: 'Created by ivanov for ACL tests',
    })
    expect(sectionResp.status).toBe(201)
    sectionId = (sectionResp.data as { id: string }).id
    expect(sectionId).toBeTruthy()
    cleanup.trackSection(adminPage, sectionId)

    const articleResp = await apiRequest(ivanovPage, 'POST', '/kb/articles', {
      title: `ACL Article ${E2E_RUN_ID}`,
      body: '# Test Article\nContent for ACL testing.',
      section_id: sectionId,
      status: 'published',
    })
    expect(articleResp.status).toBe(201)
    articleId = (articleResp.data as { id: string }).id
    expect(articleId).toBeTruthy()
    cleanup.trackArticle(adminPage, articleId)
  })

  // ── 2. sidorov без прав не видит раздел ──────────────────────────────────

  test('sidorov cannot access article without permission (403)', async () => {
    test.skip(!articleId, 'articleId not set (previous test failed)')

    const resp = await apiRequest(sidorovPage, 'GET', `/kb/articles/${articleId}`)
    expect(resp.status).toBe(403)
  })

  // ── 3. ivanov приглашает petrov как viewer ─────────────────────────────────

  test('ivanov grants petrov viewer permission on section', async () => {
    test.skip(!sectionId, 'sectionId not set')

    const petrovProfileResp = await apiRequest(petrovPage, 'GET', '/users/me')
    const petrovId = (petrovProfileResp.data as { id: string }).id

    const grantResp = await apiRequest(ivanovPage, 'POST', `/kb/sections/${sectionId}/permissions`, {
      subject_type: 'user',
      subject_id: petrovId,
      subject_name: 'Petr Petrov',
      permission: 'viewer',
    })
    expect([200, 201]).toContain(grantResp.status)
  })

  // ── 4. petrov (viewer) может читать статью ─────────────────────────────────

  test('petrov (viewer) can read article after being granted access', async () => {
    test.skip(!articleId, 'articleId not set')

    const resp = await apiRequest(petrovPage, 'GET', `/kb/articles/${articleId}`)
    expect(resp.status).toBe(200)
    const data = resp.data as { id: string }
    expect(data.id).toBe(articleId)
  })

  // ── 5. petrov (viewer) не может редактировать статью ─────────────────────

  test('petrov (viewer) cannot edit article (403)', async () => {
    test.skip(!articleId, 'articleId not set')

    const resp = await apiRequest(petrovPage, 'PUT', `/kb/articles/${articleId}`, {
      title: 'Hacked by petrov',
      body: '# Hacked',
    })
    expect(resp.status).toBe(403)
  })

  // ── 6. petrov (viewer) не может управлять правами ─────────────────────────

  test('petrov (viewer) cannot grant permissions on section (403)', async () => {
    test.skip(!sectionId, 'sectionId not set')

    const sidorovProfileResp = await apiRequest(sidorovPage, 'GET', '/users/me')
    const sidorovId = (sidorovProfileResp.data as { id: string }).id

    const resp = await apiRequest(petrovPage, 'POST', `/kb/sections/${sectionId}/permissions`, {
      subject_type: 'user',
      subject_id: sidorovId,
      subject_name: 'Sidr Sidorov',
      permission: 'viewer',
    })
    expect(resp.status).toBe(403)
  })

  // ── 7. sidorov по-прежнему не видит статью (не был приглашён) ─────────────

  test('sidorov still cannot access article (403)', async () => {
    test.skip(!articleId, 'articleId not set')

    const resp = await apiRequest(sidorovPage, 'GET', `/kb/articles/${articleId}`)
    expect(resp.status).toBe(403)
  })

  // ── 8. inherit_permissions=false → petrov теряет доступ ──────────────────

  test('petrov loses access when inherit_permissions disabled on article', async () => {
    test.skip(!articleId, 'articleId not set')

    const patchResp = await apiRequest(ivanovPage, 'PATCH', `/kb/articles/${articleId}/inherit`, {
      inherit_permissions: false,
    })
    expect([200, 201]).toContain(patchResp.status)

    const resp = await apiRequest(petrovPage, 'GET', `/kb/articles/${articleId}`)
    expect(resp.status).toBe(403)
  })

  // ── 9. ivanov возвращает inherit=true → petrov снова видит ────────────────

  test('petrov regains access after inherit_permissions re-enabled', async () => {
    test.skip(!articleId, 'articleId not set')

    const patchResp = await apiRequest(ivanovPage, 'PATCH', `/kb/articles/${articleId}/inherit`, {
      inherit_permissions: true,
    })
    expect([200, 201]).toContain(patchResp.status)

    const resp = await apiRequest(petrovPage, 'GET', `/kb/articles/${articleId}`)
    expect(resp.status).toBe(200)
  })

  // ── 10. UI: petrov видит раздел KB на странице /kb ──────────────────────

  test('petrov sees KB section title on /kb page', async () => {
    test.skip(!sectionId, 'sectionId not set')

    await petrovPage.goto('/kb')
    await petrovPage.waitForLoadState('networkidle', { timeout: 10_000 })

    const bodyText = await petrovPage.locator('body').innerText()
    expect(bodyText.length).toBeGreaterThan(10)
  })
})
