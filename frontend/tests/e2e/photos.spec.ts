import { test, expect, Browser, Page } from '@playwright/test'

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
      try { data = await resp.json() } catch { data = null }
      return { status: resp.status, data }
    },
    { method, path, body, csrf },
  )
}

async function apiUploadPhoto(
  page: Page,
  folderId: string,
  pngBytes: number[],
): Promise<{ status: number; data: unknown }> {
  const csrf = await getCsrfToken(page)
  return page.evaluate(
    async ({ folderId, pngBytes, csrf }) => {
      const bytes = new Uint8Array(pngBytes)
      const blob = new Blob([bytes], { type: 'image/png' })
      const form = new FormData()
      form.append('files', blob, 'test-photo.png')
      const resp = await fetch(`/api/v1/photos/folders/${folderId}/upload`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-CSRF-Token': csrf },
        body: form,
      })
      let data: unknown
      try { data = await resp.json() } catch { data = null }
      return { status: resp.status, data }
    },
    { folderId, pngBytes, csrf },
  )
}

async function createLocalUser(
  adminPage: Page,
  email: string,
  fullName: string,
  password: string,
  role: 'reader' | 'editor' | 'admin' = 'reader',
): Promise<string | null> {
  const result = await apiJson(adminPage, 'POST', '/admin/users/local', {
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

const MINIMAL_PNG = [
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
  0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
  0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
  0xde, 0x00, 0x00, 0x00, 0x0c, 0x49, 0x44, 0x41,
  0x54, 0x08, 0xd7, 0x63, 0xf8, 0xcf, 0xc0, 0x00,
  0x00, 0x00, 0x02, 0x00, 0x01, 0xe2, 0x21, 0xbc,
  0x33, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e,
  0x44, 0xae, 0x42, 0x60, 0x82,
]

test.describe('Photos gallery', () => {
  test.skip(skip, 'E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD не заданы')

  let adminPage: Page
  let folderId: string
  let photoId: string
  let shareToken: string
  const folderName = `E2E Gallery ${Date.now()}`

  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext()
    adminPage = await context.newPage()
    await localLogin(adminPage, adminEmail!, adminPassword!)
  })

  test.afterAll(async () => {
    await adminPage?.context().close()
  })

  test('create folder → upload photo → thumbnail appears in grid', async () => {
    const folderResp = await apiJson(adminPage, 'POST', '/photos/folders', {
      parent_id: null,
      name: folderName,
    })
    expect(folderResp.status).toBe(201)
    folderId = (folderResp.data as { id: string }).id
    expect(folderId).toBeTruthy()

    const uploadResp = await apiUploadPhoto(adminPage, folderId, MINIMAL_PNG)
    expect([200, 201]).toContain(uploadResp.status)
    const items = (uploadResp.data as { items: Array<{ photo_id: string; ok: boolean }> }).items
    expect(items.length).toBeGreaterThan(0)
    expect(items[0].ok).toBe(true)
    photoId = items[0].photo_id
    expect(photoId).toBeTruthy()

    const photosResp = await apiJson(adminPage, 'GET', `/photos/folders/${folderId}/photos`)
    expect(photosResp.status).toBe(200)
    const photoItems = (photosResp.data as { items: Array<{ id: string }> }).items
    expect(photoItems.length).toBeGreaterThan(0)
    expect(photoItems.some((p) => p.id === photoId)).toBe(true)
  })

  test('share link flow: create share link → public URL loads photo without auth', async ({ browser }) => {
    test.skip(!photoId, 'photoId not set (previous test failed)')

    const shareResp = await apiJson(adminPage, 'POST', `/photos/${photoId}/share`, {
      expires_in_days: 7,
    })
    expect([200, 201]).toContain(shareResp.status)
    shareToken = (shareResp.data as { token: string }).token
    expect(shareToken).toBeTruthy()

    const publicContext = await browser.newContext()
    const publicPage = await publicContext.newPage()

    try {
      await publicPage.goto(`/p/${shareToken}`)
      await publicPage.waitForLoadState('networkidle', { timeout: 15_000 })

      const body = publicPage.locator('body')
      await expect(body).toBeVisible()

      const errorEl = publicPage.locator('.public-photo__state--error')
      expect(await errorEl.count()).toBe(0)

      const infoResp = await publicPage.evaluate(
        async ({ token }) => {
          const resp = await fetch(`/api/v1/photos/public/${encodeURIComponent(token)}/info`)
          return { status: resp.status }
        },
        { token: shareToken },
      )
      expect(infoResp.status).toBe(200)
    } finally {
      await publicContext.close()
    }
  })

  test('ACL: user without folder permissions cannot see folder', async ({ browser }) => {
    test.skip(!folderId, 'folderId not set (previous test failed)')

    const readerEmail = `reader-e2e-${Date.now()}@portal.local`
    const readerPassword = 'TestP@ss1!'
    await createLocalUser(adminPage, readerEmail, 'Reader User', readerPassword, 'reader')

    const readerContext = await browser.newContext()
    const readerPage = await readerContext.newPage()

    try {
      await localLogin(readerPage, readerEmail, readerPassword)

      const folderResp = await apiJson(readerPage, 'GET', `/photos/folders/${folderId}`)
      expect([403, 404]).toContain(folderResp.status)

      const photosResp = await apiJson(readerPage, 'GET', `/photos/folders/${folderId}/photos`)
      expect([403, 404]).toContain(photosResp.status)
    } finally {
      await readerContext.close()
    }
  })
})
