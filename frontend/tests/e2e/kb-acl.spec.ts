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
 *   4. inherit_permissions=false: существующие гранты копируются на статью,
 *      новые секционные гранты статьёй не наследуются; re-enable возвращает наследование
 */
import { test, expect, Page } from './lib/test'
import { CleanupRegistry, apiRequest, e2eContextOptions, newAdminPage } from './fixtures/api'
import { E2E_RUN_ID, runScopedEmail } from './fixtures/run-id'

const adminEmail = process.env.E2E_ADMIN_EMAIL
const adminPassword = process.env.E2E_ADMIN_PASSWORD

const skip = !adminEmail || !adminPassword

// ─── helpers ──────────────────────────────────────────────────────────────────

async function localLogin(page: Page, email: string, password: string) {
  await page.goto('/auth/local')
  const emailInput = page.locator('input[autocomplete="email"]').first()
  await emailInput.waitFor({ timeout: 10_000 })
  await emailInput.fill(email)
  await page.locator('input[type="password"]').first().fill(password)
  await page.getByRole('button', { name: /войти|log in|sign in/i }).first().click()
  await page.waitForURL((url) => !url.pathname.startsWith('/auth/'), { timeout: 15_000 })
}

// ─── fixture: create test users via admin API ──────────────────────────────

async function createLocalUser(
  adminPage: Page,
  email: string,
  fullName: string,
  password: string,
  role: 'reader' | 'editor' | 'admin' = 'reader',
): Promise<string> {
  const result = await apiRequest(adminPage, 'POST', '/users/admin/local', {
    email,
    full_name: fullName,
    password,
    role,
  })
  // Молчаливый null превращался позже в невнятный таймаут логина — валим сразу
  // с понятной причиной. Эндпоинт отвечает 200 (response_model без 201).
  expect(
    result.status,
    `failed to create user ${email}: ${JSON.stringify(result.data)}`,
  ).toBe(200)
  return (result.data as { id: string }).id
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
  let articleVersion: number
  const cleanup = new CleanupRegistry()

  test.beforeAll(async ({ browser }) => {
    // Admin-сессия — из setup-проекта (один логин на весь прогон, см. auth.setup.ts).
    adminPage = await newAdminPage(browser)

    // review-2 (P2): трекать каждого пользователя СРАЗУ после создания —
    // прежде регистрация шла после всех трёх, и падение на втором/третьем
    // оставляло созданных без cleanup
    const ivanovId = await createLocalUser(adminPage, ivanovEmail, 'Ivan Ivanov', testPassword, 'editor')
    cleanup.trackUser(adminPage, ivanovId)
    const petrovId = await createLocalUser(adminPage, petrovEmail, 'Petr Petrov', testPassword, 'reader')
    cleanup.trackUser(adminPage, petrovId)
    const sidorovId = await createLocalUser(adminPage, sidorovEmail, 'Sidr Sidorov', testPassword, 'reader')
    cleanup.trackUser(adminPage, sidorovId)

    const ivanovContext = await browser.newContext(e2eContextOptions())
    ivanovPage = await ivanovContext.newPage()
    await localLogin(ivanovPage, ivanovEmail, testPassword)

    const petrovContext = await browser.newContext(e2eContextOptions())
    petrovPage = await petrovContext.newPage()
    await localLogin(petrovPage, petrovEmail, testPassword)

    const sidorovContext = await browser.newContext(e2eContextOptions())
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
    const article = articleResp.data as { id: string; version: number }
    articleId = article.id
    articleVersion = article.version
    expect(articleId).toBeTruthy()
    cleanup.trackArticle(adminPage, articleId)
  })

  // ── 2. sidorov без прав не видит раздел ──────────────────────────────────

  test('sidorov cannot access article without permission (403)', async () => {
    test.skip(!articleId, 'articleId not set (previous test failed)')

    const resp = await apiRequest(sidorovPage, 'GET', `/kb/articles/${articleId}`)
    expect(resp.status).toBe(403)

    // Аудит-4 (P2): «не видит раздел» — это не только 403 по прямой ссылке:
    // приватный раздел обязан отсутствовать в СПИСКЕ секций sidorov
    // (утечка через list-эндпоинт проходила незаметно).
    const sectionsResp = await apiRequest(sidorovPage, 'GET', '/kb/sections')
    expect(sectionsResp.status).toBe(200)
    const sections = (sectionsResp.data as { items: { id: string }[] }).items ?? []
    expect(
      sections.some((sec) => sec.id === sectionId),
      'приватный раздел утекает в список секций sidorov',
    ).toBe(false)
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

    // version обязателен (optimistic locking): без него Pydantic отдаёт 422
    // до проверки прав, а тест проверяет именно ACL (403).
    const resp = await apiRequest(petrovPage, 'PUT', `/kb/articles/${articleId}`, {
      title: 'Hacked by petrov',
      body: '# Hacked',
      version: articleVersion,
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

  // ── 8. inherit_permissions=false → новые гранты секции не наследуются ─────
  // NB: существующие секционные права при отключении наследования КОПИРУЮТСЯ
  // на уровень статьи (permissions.py: set_inherit_permissions), поэтому
  // petrov сохраняет доступ; теряют его новые гранты, выданные после отключения.

  test('article stops inheriting new section grants when inherit disabled', async () => {
    test.skip(!sectionId || !articleId, 'ids not set')

    const patchResp = await apiRequest(ivanovPage, 'PATCH', `/kb/articles/${articleId}/inherit`, {
      inherit_permissions: false,
    })
    expect([200, 201]).toContain(patchResp.status)

    // petrov сохраняет доступ: его viewer скопирован в kb_article_permissions
    const petrovResp = await apiRequest(petrovPage, 'GET', `/kb/articles/${articleId}`)
    expect(petrovResp.status).toBe(200)

    // новый секционный грант (sidorov) статья больше не наследует
    const sidorovProfileResp = await apiRequest(sidorovPage, 'GET', '/users/me')
    const sidorovId = (sidorovProfileResp.data as { id: string }).id
    const grantResp = await apiRequest(ivanovPage, 'POST', `/kb/sections/${sectionId}/permissions`, {
      subject_type: 'user',
      subject_id: sidorovId,
      subject_name: 'Sidr Sidorov',
      permission: 'viewer',
    })
    expect([200, 201]).toContain(grantResp.status)

    const sidorovResp = await apiRequest(sidorovPage, 'GET', `/kb/articles/${articleId}`)
    expect(sidorovResp.status).toBe(403)
  })

  // ── 9. inherit=true → секционные гранты снова действуют для статьи ────────

  test('section grants reach article again after inherit re-enabled', async () => {
    test.skip(!sectionId || !articleId, 'ids not set')

    const patchResp = await apiRequest(ivanovPage, 'PATCH', `/kb/articles/${articleId}/inherit`, {
      inherit_permissions: true,
    })
    expect([200, 201]).toContain(patchResp.status)

    // sidorov получил секционный viewer в тесте 8 — теперь статья наследует его
    const sidorovResp = await apiRequest(sidorovPage, 'GET', `/kb/articles/${articleId}`)
    expect(sidorovResp.status).toBe(200)

    const petrovResp = await apiRequest(petrovPage, 'GET', `/kb/articles/${articleId}`)
    expect(petrovResp.status).toBe(200)
  })

  // ── 10. UI: petrov видит раздел KB на странице /kb ──────────────────────

  test('petrov sees KB section title on /kb page', async () => {
    test.skip(!sectionId, 'sectionId not set')

    await petrovPage.goto('/kb')
    // networkidle на авторизованных страницах не наступает из-за открытого
    // SSE-потока /notifications/stream — ждём конкретный контент.
    await expect(petrovPage.getByText(`ACL Section ${E2E_RUN_ID}`).first()).toBeVisible({
      timeout: 10_000,
    })
  })
})
