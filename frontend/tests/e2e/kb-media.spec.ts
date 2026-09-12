/**
 * E2E KB Медиа — вставка изображения, экспорт MD, импорт Obsidian vault.
 *
 * Требует работающий стек:
 *   - backend на порту 8000 (proxied через vite на /api)
 *   - LOCAL_AUTH_ENABLED=true
 *   - E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD
 *
 * Тесты автоматически пропускаются если переменные окружения не заданы.
 *
 * Сценарии:
 *   1. editor создаёт статью и загружает изображение → URL появляется в ответе
 *   2. Экспорт статьи в Markdown → ответ содержит frontmatter с заголовком
 *   3. Импорт .md файла → статья создаётся в KB
 *   4. Импорт Obsidian vault (.zip) → статьи создаются из ZIP
 *   5. Экспорт раздела (.zip) → ZIP содержит .md файлы
 */
import { test, expect, Page } from './lib/test'
import { CleanupRegistry, getCsrfToken, newAdminPage } from './fixtures/api'
import { makeStoredZip, readZipEntries } from './fixtures/zip'
import { E2E_RUN_ID } from './fixtures/run-id'

const adminEmail = process.env.E2E_ADMIN_EMAIL
const adminPassword = process.env.E2E_ADMIN_PASSWORD

const skip = !adminEmail || !adminPassword

// ─── helpers ──────────────────────────────────────────────────────────────────

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
          'X-XSRF-TOKEN': csrf,
        },
        body: body != null ? JSON.stringify(body) : undefined,
      })
      let data: unknown
      try { data = await resp.json() } catch { data = null }
      return { status: resp.status, data }
    },
    { method, path, body, csrf },
  )
}

async function apiGetBytes(
  page: Page,
  path: string,
): Promise<{ status: number; contentType: string; text: string; size: number; b64: string }> {
  const csrf = await getCsrfToken(page)
  return page.evaluate(
    async ({ path, csrf }) => {
      const resp = await fetch(`/api/v1${path}`, {
        method: 'GET',
        credentials: 'include',
        headers: { 'X-XSRF-TOKEN': csrf },
      })
      const buffer = await resp.arrayBuffer()
      const text = new TextDecoder('utf-8').decode(buffer)
      // base64-байты для бинарно-точного разбора (ZIP) — utf-8 text лоссят
      let binary = ''
      const bytes = new Uint8Array(buffer)
      const chunk = 0x8000
      for (let i = 0; i < bytes.length; i += chunk) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunk))
      }
      return {
        status: resp.status,
        contentType: resp.headers.get('content-type') || '',
        text,
        size: buffer.byteLength,
        b64: btoa(binary),
      }
    },
    { path, csrf },
  )
}

async function apiUploadFile(
  page: Page,
  path: string,
  fieldName: string,
  filename: string,
  mimeType: string,
  content: string | Uint8Array,
): Promise<{ status: number; data: unknown }> {
  const csrf = await getCsrfToken(page)
  const contentBase64 = typeof content === 'string'
    ? btoa(unescape(encodeURIComponent(content)))
    : Buffer.from(content).toString('base64')

  return page.evaluate(
    async ({ path, fieldName, filename, mimeType, contentBase64, csrf }) => {
      const binary = atob(contentBase64)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
      const blob = new Blob([bytes], { type: mimeType })
      const form = new FormData()
      form.append(fieldName, blob, filename)
      const resp = await fetch(`/api/v1${path}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-XSRF-TOKEN': csrf },
        body: form,
      })
      let data: unknown
      try { data = await resp.json() } catch { data = null }
      return { status: resp.status, data }
    },
    { path, fieldName, filename, mimeType, contentBase64, csrf },
  )
}

// ─── test suite ───────────────────────────────────────────────────────────────

test.describe('KB Media: upload, export, import', () => {
  test.describe.configure({ mode: 'serial' })
  test.skip(skip, 'E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD не заданы')

  let page: Page
  let sectionId: string
  let articleId: string
  const articleTitle = `Media Article ${E2E_RUN_ID}`
  const cleanup = new CleanupRegistry()

  test.beforeAll(async ({ browser }) => {
    // Admin-сессия — из setup-проекта (один логин на весь прогон, см. auth.setup.ts).
    page = await newAdminPage(browser)
  })

  test.afterAll(async () => {
    try {
      await cleanup.flush()
    } finally {
      await page?.context().close()
    }
  })

  // ── Setup: create section and article ──────────────────────────────────────

  test('setup: create section and article', async () => {
    const secResp = await apiJson(page, 'POST', '/kb/sections', {
      title: `Media Section ${E2E_RUN_ID}`,
    })
    expect(secResp.status).toBe(201)
    sectionId = (secResp.data as { id: string }).id
    cleanup.trackSection(page, sectionId)

    const artResp = await apiJson(page, 'POST', '/kb/articles', {
      title: articleTitle,
      body: '# Media Test\nThis article is for media upload testing.',
      section_id: sectionId,
      status: 'published',
    })
    expect(artResp.status).toBe(201)
    articleId = (artResp.data as { id: string }).id
    expect(articleId).toBeTruthy()
    cleanup.trackArticle(page, articleId)
  })

  // ── 1. Загрузка изображения → URL в ответе ─────────────────────────────────

  test('upload image to article → URL returned with article ID', async () => {
    test.skip(!articleId, 'articleId not set')

    const pngBytes = new Uint8Array([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
      0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
      0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
      0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
      0xde, 0x00, 0x00, 0x00, 0x0c, 0x49, 0x44, 0x41,
      0x54, 0x08, 0xd7, 0x63, 0xf8, 0xcf, 0xc0, 0x00,
      0x00, 0x00, 0x02, 0x00, 0x01, 0xe2, 0x21, 0xbc,
      0x33, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e,
      0x44, 0xae, 0x42, 0x60, 0x82,
    ])

    const resp = await apiUploadFile(
      page,
      `/kb/articles/${articleId}/media`,
      'file',
      'test-image.png',
      'image/png',
      pngBytes,
    )

    expect([200, 201]).toContain(resp.status)
    const data = resp.data as { url: string; filename: string }
    expect(data.url).toBeTruthy()
    expect(data.url).toContain(articleId)
    expect(data.filename).toBeTruthy()
  })

  // ── 2. Экспорт статьи в Markdown → frontmatter с заголовком ──────────────

  test('export article to Markdown → frontmatter contains title', async () => {
    test.skip(!articleId, 'articleId not set')

    const result = await apiGetBytes(page, `/kb/articles/${articleId}/export/md`)

    expect(result.status).toBe(200)
    expect(result.contentType).toContain('markdown')
    expect(result.text).toContain('---')
    expect(result.text).toContain(articleTitle)
    expect(result.text).toContain('Media Test')
  })

  // ── 3. Импорт .md файла → статья создаётся ────────────────────────────────

  test('import .md file → article created in KB', async () => {
    const uniqueTitle = `Imported Article ${Date.now()}`
    const mdContent = [
      '---',
      `title: ${uniqueTitle}`,
      'tags:',
      '  - e2e',
      '  - import',
      '---',
      '',
      '# Imported Content',
      'This article was imported from a .md file.',
    ].join('\n')

    const resp = await apiUploadFile(
      page,
      '/kb/articles/import?strategy=skip',
      'file',
      'import-test.md',
      'text/markdown',
      mdContent,
    )

    expect([200, 201]).toContain(resp.status)
    const data = resp.data as { created: number; updated: number; skipped: number; errors: string[] }
    expect(data.created).toBeGreaterThanOrEqual(1)
    expect(data.errors).toEqual([])

    const searchResp = await apiJson(page, 'GET', `/kb/articles?search=${encodeURIComponent(uniqueTitle)}`)
    const items = (searchResp.data as { items: Array<{ id: string; title: string }> }).items || []
    const created = items.filter((a) => a.title === uniqueTitle)
    expect(created.length, 'импортированная статья обязана находиться поиском')
      .toBeGreaterThanOrEqual(1)
    // review-2 (P2) + review-3: импорт создаёт статью — регистрируем в
    // cleanup ВСЕ совпадающие по заголовку (прошлые упавшие прогоны могли
    // оставить дубликаты; прежний find удалял только первый)
    for (const article of created) {
      cleanup.trackArticle(page, article.id)
    }
  })

  // ── 4. Импорт Obsidian vault ZIP → статьи создаются из ZIP ───────────────

  test('import Obsidian vault ZIP → articles created from ZIP entries', async () => {
    const title1 = `Vault Article A ${Date.now()}`
    const title2 = `Vault Article B ${Date.now()}`

    const md1 = `---\ntitle: ${title1}\ntags:\n  - vault\n---\n\n# Article A\nContent A.`
    const md2 = `---\ntitle: ${title2}\n---\n\n# Article B\nContent B.`

    const zipBytes = makeStoredZip([
      { path: 'Section A/article-a.md', data: md1 },
      { path: 'article-b.md', data: md2 },
    ])

    const resp = await apiUploadFile(
      page,
      '/kb/import/vault?strategy=skip',
      'file',
      'vault.zip',
      'application/zip',
      zipBytes,
    )

    expect([200, 201]).toContain(resp.status)
    const data = resp.data as { created: number; errors: string[] }
    // audit-review follow-up, P1: created>=1 пропускал потерю второй статьи —
    // обе обязаны создаться и находиться поиском по точным заголовкам.
    expect(data.created).toBe(2)
    expect(data.errors).toEqual([])

    for (const title of [title1, title2]) {
      const searchResp = await apiJson(
        page,
        'GET',
        `/kb/articles?search=${encodeURIComponent(title)}`,
      )
      const items = (searchResp.data as { items: Array<{ id: string; title: string }> }).items || []
      const found = items.find((a) => a.title === title)
      expect(found, `статья «${title}» обязана существовать после импорта`).toBeTruthy()
      cleanup.trackArticle(page, found!.id)
    }
  })

  // ── 5. Экспорт раздела (.zip) → ZIP содержит .md файлы ──────────────────

  test('export section as ZIP → ZIP contains .md files', async () => {
    test.skip(!sectionId, 'sectionId not set')

    const result = await apiGetBytes(page, `/kb/sections/${sectionId}/export/zip`)

    expect(result.status).toBe(200)
    expect(result.contentType).toContain('zip')

    // audit-review follow-up, P1: сигнатуры и подстроки недостаточно —
    // архив разбирается целиком (EOCD → central directory → local headers,
    // stored/deflate) с проверкой имён и содержимого записей.
    const entries = readZipEntries(Buffer.from(result.b64, 'base64'))
    expect(entries.length).toBeGreaterThan(0)

    const mdEntries = entries.filter((e) => e.path.endsWith('.md'))
    expect(mdEntries.length, 'в архиве обязаны быть .md-записи').toBeGreaterThan(0)

    const articleEntry = entries.find((e) => e.path.endsWith('.md') && e.data.includes(articleTitle))
    expect(
      articleEntry,
      `экспортированный архив обязан содержать статью «${articleTitle}» с телом`,
    ).toBeTruthy()
    expect(articleEntry!.data.toString('utf-8')).toContain('This article is for media upload testing.')
  })

  // ── 6. UI: кнопка экспорта раздела видна на странице KB ─────────────────

  test('KB list page shows export section button when section is selected', async () => {
    test.skip(!sectionId, 'sectionId not set')

    await page.goto(`/kb?section=${sectionId}`)
    await expect(
      page.getByRole('button', { name: /экспорт.*раздел|export.*section/i }),
    ).toBeVisible({ timeout: 10_000 })
  })
})
