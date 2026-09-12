import { test, expect, Page } from './lib/test'
import { CleanupRegistry, e2eContextOptions, getCsrfToken, newAdminPage } from './fixtures/api'
import { E2E_RUN_ID } from './fixtures/run-id'

const adminEmail = process.env.E2E_ADMIN_EMAIL
const adminPassword = process.env.E2E_ADMIN_PASSWORD

const skip = !adminEmail || !adminPassword

async function localLogin(page: Page, email: string, password: string) {
  await page.goto('/auth/local')
  const emailInput = page.locator('input[autocomplete="email"]').first()
  await emailInput.waitFor({ timeout: 10_000 })
  await emailInput.fill(email)
  await page.locator('input[type="password"]').first().fill(password)
  await page.getByRole('button', { name: /войти|log in|sign in/i }).first().click()
  await page.waitForURL((url) => !url.pathname.startsWith('/auth/'), { timeout: 15_000 })
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
        headers: { 'X-XSRF-TOKEN': csrf },
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
): Promise<string> {
  const result = await apiJson(adminPage, 'POST', '/users/admin/local', {
    email,
    full_name: fullName,
    password,
    role,
  })
  // Аудит-4 (P2): без silent-null — падение создания юзера должно ронять тест
  // сразу и с внятной причиной, а не таймаутом логина через 15с (как в kb-acl).
  // Контракт эндпоинта — 200 или 201 (проверено живым прогоном run #863).
  expect(
    [200, 201],
    `createLocalUser(${email}) → ${result.status}`,
  ).toContain(result.status)
  const id = (result.data as { id: string }).id
  expect(id).toBeTruthy()
  return id
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
  test.describe.configure({ mode: 'serial' })
  test.skip(skip, 'E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD не заданы')

  let adminPage: Page
  let folderId: string
  let photoId: string
  let shareToken: string
  const folderName = `E2E Gallery ${E2E_RUN_ID}`
  const cleanup = new CleanupRegistry()

  test.beforeAll(async ({ browser }) => {
    // Admin-сессия — из setup-проекта (один логин на весь прогон, см. auth.setup.ts).
    adminPage = await newAdminPage(browser)
  })

  test.afterAll(async () => {
    try {
      await cleanup.flush()
    } finally {
      await adminPage?.context().close()
    }
  })

  test('create folder → upload photo → thumbnail appears in grid', async () => {
    const folderResp = await apiJson(adminPage, 'POST', '/photos/folders', {
      parent_id: null,
      name: folderName,
    })
    expect(folderResp.status).toBe(201)
    folderId = (folderResp.data as { id: string }).id
    expect(folderId).toBeTruthy()
    cleanup.trackPhotoFolder(adminPage, folderId)

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

    const publicContext = await browser.newContext(e2eContextOptions())
    const publicPage = await publicContext.newPage()

    try {
      await publicPage.goto(`/p/${shareToken}`)
      await publicPage.waitForLoadState('networkidle', { timeout: 15_000 })

      const body = publicPage.locator('body')
      await expect(body).toBeVisible()

      const errorEl = publicPage.locator('.public-photo__state--error')
      expect(await errorEl.count()).toBe(0)

      // audit-review 2026-08-22, P1: «нет error-элемента» не доказывала, что
      // фото вообще выдаётся. Пиксельный рендер в e2e невозможен: файловая
      // выдача идёт через X-Accel-Redirect (механизм nginx; в e2e-окружении
      // nginx нет — браузер получает пустой 200, naturalWidth=0 даже на проде
      // работающей ссылки). Потому проверяем сам путь выдачи: webp-thumbnail
      // по публичному токену обязан ответить 200 + image/* + X-Accel-Redirect
      // на файл (avif-404 — штатный fallback браузера на webp-source).
      const img = publicPage.locator('img.public-photo__img')
      await expect(img).toBeVisible({ timeout: 10_000 })
      // audit-review follow-up, P1: обязательный успешный webp-delivery.
      // Браузерный <source>-фолбэк после avif-404 в e2e-окружении Chromium
      // ненадёжен (запрос webp может не последовать) — потому delivery
      // проверяем прямым запросом thumbnail из публичного контекста страницы
      // (без auth — в этом смысл share-токена), как это делает прод-клиент.
      const delivery = await publicPage.evaluate(
        async ({ token }) => {
          const resp = await fetch(
            `/api/v1/photos/public/${encodeURIComponent(token)}/thumbnail/1600`,
          )
          const headers = Object.fromEntries(resp.headers.entries())
          return { status: resp.status, contentType: headers['content-type'] || '', xaccel: headers['x-accel-redirect'] || '' }
        },
        { token: shareToken },
      )
      expect(delivery.status, 'webp-thumbnail по публичному токену обязан выдаваться').toBe(200)
      expect(delivery.contentType).toContain('image/')
      expect(
        delivery.xaccel,
        'бэкенд обязан назначить файл выдачи (X-Accel-Redirect)',
      ).toBeTruthy()

      // Аудит 2026-08-23 (P2): видимость <img> и hardcoded /thumbnail/1600
      // проверялись по отдельности — не доказывалось, что РЕАЛЬНЫЙ src
      // показанного DOM-изображения валиден. Семантика с учётом picture-
      // fallback (поймано живым прогоном run #788): браузер выбирает avif
      // <source>; когда avif-файла нет, production ОТВЕЧАЕТ 404 намеренно
      // (public_views._thumb_response) и браузер переключается на webp.
      // Инвариант: webp-источник (img.src, его проставляет PublicPhotoPage)
      // обязан отвечать 200; currentSrc (выбор браузера) — 200, либо ровно
      // 404 на format=avif (штатный fallback); любые иные статусы — дефект.
      const domDelivery = await publicPage.evaluate(async () => {
        const img = document.querySelector('img.public-photo__img') as HTMLImageElement | null
        const currentSrc = img?.currentSrc || ''
        const fallbackSrc = img?.src || ''
        const fetchStatus = async (url: string) =>
          url ? (await fetch(url)).status : 0
        return {
          currentSrc,
          fallbackSrc,
          currentStatus: await fetchStatus(currentSrc),
          fallbackStatus: await fetchStatus(fallbackSrc),
        }
      })
      expect(domDelivery.fallbackSrc, 'показанный <img> обязан несть webp src').toBeTruthy()
      // review-2 (P2): URL обязан принадлежать ИМЕННО этому share-токену —
      // иначе ассерт принял бы любое другое рабочее публичное фото
      expect(
        domDelivery.fallbackSrc,
        'DOM-URL обязан содержать текущий shareToken',
      ).toContain(shareToken)
      if (domDelivery.currentSrc) {
        expect(domDelivery.currentSrc).toContain(shareToken)
      }
      expect(
        domDelivery.fallbackStatus,
        `webp-источник DOM-изображения обязан отвечать 200 (получен ${domDelivery.fallbackStatus}, url=${domDelivery.fallbackSrc})`,
      ).toBe(200)
      const currentOk =
        domDelivery.currentStatus === 200 ||
        (domDelivery.currentStatus === 404 && domDelivery.currentSrc.includes('format=avif'))
      expect(
        currentOk,
        `currentSrc показанного изображения обязан отвечать 200 (допустим только штатный avif-404-fallback); ` +
          `получен ${domDelivery.currentStatus}, url=${domDelivery.currentSrc}`,
      ).toBe(true)

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

  test('share revoke: photo share → revoke → public API returns 404', async () => {
    test.skip(!photoId, 'photoId not set (previous test failed)')

    const shareResp = await apiJson(adminPage, 'POST', `/photos/${photoId}/share`, {
      expires_in_days: 7,
    })
    expect([200, 201]).toContain(shareResp.status)
    const revokeToken = (shareResp.data as { token: string; id: string }).token
    const revokeTokenId = (shareResp.data as { id: string }).id
    expect(revokeToken).toBeTruthy()
    expect(revokeTokenId).toBeTruthy()

    const infoBefore = await adminPage.evaluate(
      async ({ token }) => {
        const resp = await fetch(`/api/v1/photos/public/${encodeURIComponent(token)}/info`)
        return { status: resp.status }
      },
      { token: revokeToken },
    )
    expect(infoBefore.status).toBe(200)

    const revokeResp = await apiJson(adminPage, 'DELETE', `/photos/my-shares/photo/${revokeTokenId}`)
    expect(revokeResp.status).toBe(204)

    const infoAfter = await adminPage.evaluate(
      async ({ token }) => {
        const resp = await fetch(`/api/v1/photos/public/${encodeURIComponent(token)}/info`)
        return { status: resp.status }
      },
      { token: revokeToken },
    )
    // Аудит 2026-08-23 (P2): заголовок обещает 404, но принимался любой из
    // [404, 410]. Production (public_views._resolve_token): отозванный
    // photo-токен → 404 «Link not found»; 410 у photo-токена только при
    // истечении срока. Разделяем статусы между photo/folder-тестами.
    expect(infoAfter.status, 'отозванный photo-share обязан отвечать 404').toBe(404)
  })

  test('share revoke: folder share → revoke → public API returns 410', async () => {
    test.skip(!folderId, 'folderId not set (previous test failed)')

    const shareResp = await apiJson(adminPage, 'POST', `/photos/folders/${folderId}/share`, {
      expires_in_days: 7,
    })
    expect([200, 201]).toContain(shareResp.status)
    const folderShareToken = (shareResp.data as { token: string }).token
    const folderShareTokenId = (shareResp.data as { id: string }).id
    expect(folderShareToken).toBeTruthy()
    expect(folderShareTokenId).toBeTruthy()

    const infoBefore = await adminPage.evaluate(
      async ({ token }) => {
        const resp = await fetch(`/api/v1/photos/public-folder/${encodeURIComponent(token)}/info`)
        return { status: resp.status }
      },
      { token: folderShareToken },
    )
    expect(infoBefore.status).toBe(200)

    const revokeResp = await apiJson(adminPage, 'DELETE', `/photos/my-shares/folder/${folderShareTokenId}`)
    expect(revokeResp.status).toBe(204)

    const infoAfter = await adminPage.evaluate(
      async ({ token }) => {
        const resp = await fetch(`/api/v1/photos/public-folder/${encodeURIComponent(token)}/info`)
        return { status: resp.status }
      },
      { token: folderShareToken },
    )
    // Аудит 2026-08-23 (P2): production (public_views._resolve_folder_token_
    // sync_check) для отозванного folder-токена возвращает 410 Gone —
    // ровно его и требуем (прежде принимался и 404).
    expect(infoAfter.status, 'отозванный folder-share обязан отвечать 410').toBe(410)
  })

  test('share TTL: creates share with expires_at in future, API returns expires_at field', async () => {
    test.skip(!photoId, 'photoId not set (previous test failed)')

    const beforeCreate = Date.now()
    const shareResp = await apiJson(adminPage, 'POST', `/photos/${photoId}/share`, {
      expires_in_days: 1,
    })
    expect([200, 201]).toContain(shareResp.status)
    const data = shareResp.data as { token: string; expires_at: string }
    expect(data.expires_at).toBeTruthy()

    const expiresAt = new Date(data.expires_at).getTime()
    expect(expiresAt).toBeGreaterThan(beforeCreate)
    expect(expiresAt).toBeGreaterThan(Date.now() + 23 * 3600 * 1000)

    const infoResp = await adminPage.evaluate(
      async ({ token }) => {
        const resp = await fetch(`/api/v1/photos/public/${encodeURIComponent(token)}/info`)
        return { status: resp.status }
      },
      { token: data.token },
    )
    expect(infoResp.status).toBe(200)
  })

  test('ACL: user without folder permissions cannot see folder', async ({ browser }) => {
    test.skip(!folderId, 'folderId not set (previous test failed)')

    const readerEmail = `reader-${E2E_RUN_ID}@portal.local`
    const readerPassword = 'TestP@ss1!'
    const readerId = await createLocalUser(adminPage, readerEmail, 'Reader User', readerPassword, 'reader')
    cleanup.trackUser(adminPage, readerId)

    const readerContext = await browser.newContext(e2eContextOptions())
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
