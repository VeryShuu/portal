/**
 * Helpers для e2e-тестов: вход и API-запросы из контекста уже залогиненной страницы,
 * плюс утилиты для трекинга и удаления созданных сущностей (cleanup в afterEach/afterAll).
 *
 * Используется в kb-acl/kb-media/photos спеках, чтобы не оставлять мусор в БД
 * между запусками (см. test.md, §1.3).
 */
import type { Page } from '@playwright/test'

export interface ApiResponse<T = unknown> {
  status: number
  data: T | null
}

export async function localLogin(page: Page, email: string, password: string): Promise<void> {
  await page.goto('/login')
  const emailInput = page.locator('input[type="email"], input[name="email"]').first()
  await emailInput.waitFor({ timeout: 10_000 })
  await emailInput.fill(email)
  await page.locator('input[type="password"]').first().fill(password)
  await page
    .getByRole('button', { name: /войти|log in|sign in/i })
    .first()
    .click()
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15_000 })
}

export async function apiRequest<T = unknown>(
  page: Page,
  method: string,
  path: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  return page.evaluate(
    async ({ method, path, body }) => {
      const csrfResp = await fetch('/api/v1/auth/csrf-token', { credentials: 'include' })
      const csrfJson = (await csrfResp.json().catch(() => ({}))) as { csrf_token?: string }
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
      let data: unknown = null
      try {
        data = await resp.json()
      } catch {
        data = null
      }
      return { status: resp.status, data }
    },
    { method, path, body },
  ) as Promise<ApiResponse<T>>
}

/**
 * Трекер созданных за тест сущностей. Используется в afterEach/afterAll
 * для гарантированного удаления, чтобы повторные запуски не накапливали
 * мусор и не падали на UNIQUE-конфликтах.
 */
export class CleanupRegistry {
  private readonly tasks: Array<() => Promise<void>> = []

  add(task: () => Promise<void>): void {
    this.tasks.push(task)
  }

  trackUser(adminPage: Page, userId: string): void {
    this.add(async () => {
      await apiRequest(adminPage, 'DELETE', `/users/admin/${userId}`)
    })
  }

  trackSection(adminPage: Page, sectionId: string): void {
    this.add(async () => {
      await apiRequest(adminPage, 'DELETE', `/kb/sections/${sectionId}`)
    })
  }

  trackArticle(adminPage: Page, articleId: string): void {
    this.add(async () => {
      await apiRequest(adminPage, 'DELETE', `/kb/articles/${articleId}`)
    })
  }

  trackPhotoFolder(adminPage: Page, folderId: string): void {
    this.add(async () => {
      await apiRequest(adminPage, 'DELETE', `/photos/folders/${folderId}`)
    })
  }

  /** Выполнить все cleanup-задачи в обратном порядке (LIFO). Ошибки — best-effort. */
  async flush(): Promise<void> {
    while (this.tasks.length > 0) {
      const task = this.tasks.pop()!
      try {
        await task()
      } catch {
        // Не маскируем результат теста: cleanup — best-effort.
      }
    }
  }
}
