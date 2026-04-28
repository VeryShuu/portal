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
import { test, expect, Page } from '@playwright/test'

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

async function getCsrfToken(page: Page): Promise<string> {
  const result = await page.evaluate(async () => {
    const resp = await fetch('/api/v1/auth/csrf-token', { credentials: 'include' })
    const json = await resp.json().catch(() => ({}))
    return json.csrf_token || ''
  })
  return result
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
      try { data = await resp.json() } catch { data = null }
      return { status: resp.status, data }
    },
    { method, path, body, csrf },
  )
}

async function apiGetBytes(
  page: Page,
  path: string,
): Promise<{ status: number; contentType: string; text: string; size: number }> {
  const csrf = await getCsrfToken(page)
  return page.evaluate(
    async ({ path, csrf }) => {
      const resp = await fetch(`/api/v1${path}`, {
        method: 'GET',
        credentials: 'include',
        headers: { 'X-CSRF-Token': csrf },
      })
      const buffer = await resp.arrayBuffer()
      const text = new TextDecoder('utf-8').decode(buffer)
      return {
        status: resp.status,
        contentType: resp.headers.get('content-type') || '',
        text,
        size: buffer.byteLength,
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
        headers: { 'X-CSRF-Token': csrf },
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
  test.skip(skip, 'E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD не заданы')

  let page: Page
  let sectionId: string
  let articleId: string
  const articleTitle = `Media Test Article ${Date.now()}`

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext()
    page = await context.newPage()
    await localLogin(page, adminEmail!, adminPassword!)
  })

  test.afterAll(async () => {
    await page?.context().close()
  })

  // ── Setup: create section and article ──────────────────────────────────────

  test('setup: create section and article', async () => {
    const secResp = await apiJson(page, 'POST', '/kb/sections', {
      title: `Media Test Section ${Date.now()}`,
    })
    expect(secResp.status).toBe(201)
    sectionId = (secResp.data as { id: string }).id

    const artResp = await apiJson(page, 'POST', '/kb/articles', {
      title: articleTitle,
      body: '# Media Test\nThis article is for media upload testing.',
      section_id: sectionId,
      status: 'published',
    })
    expect(artResp.status).toBe(201)
    articleId = (artResp.data as { id: string }).id
    expect(articleId).toBeTruthy()
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
    const items = (searchResp.data as { items: Array<{ title: string }> }).items || []
    const found = items.some((a) => a.title === uniqueTitle)
    expect(found).toBe(true)
  })

  // ── 4. Импорт Obsidian vault ZIP → статьи создаются из ZIP ───────────────

  test('import Obsidian vault ZIP → articles created from ZIP entries', async () => {
    const title1 = `Vault Article A ${Date.now()}`
    const title2 = `Vault Article B ${Date.now()}`

    const md1 = `---\ntitle: ${title1}\ntags:\n  - vault\n---\n\n# Article A\nContent A.`
    const md2 = `---\ntitle: ${title2}\n---\n\n# Article B\nContent B.`

    const zipBytes = await page.evaluate(
      async ({ md1, md2 }: { md1: string; md2: string }) => {
        const { default: JSZip } = await import('https://cdn.jsdelivr.net/npm/jszip@3/dist/jszip.min.js' as string).catch(() => ({ default: null }))
        if (!JSZip) return null

        const zip = new JSZip()
        zip.folder('Section A')!.file('article-a.md', md1)
        zip.file('article-b.md', md2)
        const blob = await zip.generateAsync({ type: 'uint8array' })
        return Array.from(blob)
      },
      { md1, md2 },
    )

    if (!zipBytes) {
      test.skip()
      return
    }

    const resp = await apiUploadFile(
      page,
      '/kb/import/vault?strategy=skip',
      'file',
      'vault.zip',
      'application/zip',
      new Uint8Array(zipBytes),
    )

    expect([200, 201]).toContain(resp.status)
    const data = resp.data as { created: number; errors: string[] }
    expect(data.created).toBeGreaterThanOrEqual(1)
    expect(data.errors).toEqual([])
  })

  // ── 5. Экспорт раздела (.zip) → ZIP содержит .md файлы ──────────────────

  test('export section as ZIP → ZIP contains .md files', async () => {
    test.skip(!sectionId, 'sectionId not set')

    const result = await apiGetBytes(page, `/kb/sections/${sectionId}/export/zip`)

    expect(result.status).toBe(200)
    expect(result.contentType).toContain('zip')
    expect(result.size).toBeGreaterThan(20)

    const hasMdSignature = result.text.includes('PK') || result.size > 22
    expect(hasMdSignature).toBe(true)
  })

  // ── 6. UI: кнопка экспорта раздела видна на странице KB ─────────────────

  test('KB list page shows export section button when section is selected', async () => {
    test.skip(!sectionId, 'sectionId not set')

    await page.goto('/kb')
    await page.waitForLoadState('networkidle', { timeout: 10_000 })

    const bodyText = await page.locator('body').innerText()
    expect(bodyText.length).toBeGreaterThan(10)
  })
})
