/**
 * Helpers для e2e-тестов: вход и API-запросы из контекста уже залогиненной страницы,
 * плюс утилиты для трекинга и удаления созданных сущностей (cleanup в afterEach/afterAll).
 *
 * Используется в kb-acl/kb-media/photos спеках, чтобы не оставлять мусор в БД
 * между запусками (см. test.md, §1.3).
 */
import type { Browser, BrowserContextOptions, Page } from '@playwright/test'

export interface ApiResponse<T = unknown> {
  status: number
  data: T | null
}

/**
 * StorageState единственного admin-логина (см. auth.setup.ts). Спеки создают
 * контексты через `adminContextOptions()` вместо повторного логина — иначе
 * email-лимит `/auth/local/login` (10/15 мин) исчерпывается на 4-м спеке.
 */
export const ADMIN_STATE_FILE = 'playwright/.auth/admin.json'

export function e2eContextOptions(): BrowserContextOptions {
  return process.env.E2E_REAL_IP
    ? { extraHTTPHeaders: { 'X-Real-IP': process.env.E2E_REAL_IP } }
    : {}
}

/** Контекст с готовой admin-сессией из setup-проекта (+ trusted IP для лимитов). */
export function adminContextOptions(): BrowserContextOptions {
  return { storageState: ADMIN_STATE_FILE, ...e2eContextOptions() }
}

/**
 * Страница с admin-сессией, готовая к API-вызовам: без навигации страница
 * висит на about:blank (opaque origin) — document.cookie и относительный
 * fetch там недоступны (SecurityError).
 */
export async function newAdminPage(browser: Browser): Promise<Page> {
  const context = await browser.newContext(adminContextOptions())
  const page = await context.newPage()
  await page.goto('/')
  return page
}

export async function getCsrfToken(page: Page): Promise<string> {
  // Читаем из контекста, а не из document.cookie: страница может находиться
  // на любом URL (в т.ч. до первой навигации).
  const cookies = await page.context().cookies()
  const raw = cookies.find((c) => c.name === 'XSRF-TOKEN')?.value
  if (!raw) throw new Error('XSRF-TOKEN cookie is missing')
  return decodeURIComponent(raw)
}

export async function apiRequest<T = unknown>(
  page: Page,
  method: string,
  path: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  const csrfToken = await getCsrfToken(page)
  return page.evaluate(
    async ({ method, path, body, csrfToken }) => {
      const resp = await fetch(`/api/v1${path}`, {
        method,
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-XSRF-TOKEN': csrfToken,
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
    { method, path, body, csrfToken },
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
    this.deleteChecked(adminPage, `/users/admin/${userId}`)
  }

  /**
   * DELETE с проверкой исхода (audit-review 2026-08-22, P1 «cleanup
   * проглатывает DELETE-ошибки»): 2xx или 404 (уже удалено) — норма,
   * любой другой статус — ошибка cleanup, а не молчаливый мусор в БД.
   */
  private deleteChecked(adminPage: Page, path: string): void {
    this.add(async () => {
      const resp = await apiRequest(adminPage, 'DELETE', path)
      if (resp.status >= 400 && resp.status !== 404) {
        throw new Error(`cleanup DELETE ${path} → HTTP ${resp.status}`)
      }
    })
  }

  trackSection(adminPage: Page, sectionId: string): void {
    this.deleteChecked(adminPage, `/kb/sections/${sectionId}`)
  }

  trackArticle(adminPage: Page, articleId: string): void {
    this.deleteChecked(adminPage, `/kb/articles/${articleId}`)
  }

  trackPhotoFolder(adminPage: Page, folderId: string): void {
    this.deleteChecked(adminPage, `/photos/folders/${folderId}`)
  }

  /**
   * Выполнить все cleanup-задачи в обратном порядке (LIFO).
   * Все задачи выполняются даже при ошибках; сами ошибки логируются
   * громко и проваливают прогон агрегированно (audit-review 2026-08-22,
   * P1: молчаливый cleanup оставлял тестовый мусор в БД незамеченным).
   */
  async flush(): Promise<void> {
    const errors: unknown[] = []
    while (this.tasks.length > 0) {
      const task = this.tasks.pop()!
      try {
        await task()
      } catch (err) {
        errors.push(err)
        console.error('[cleanup] задача упала:', err)
      }
    }
    if (errors.length > 0) {
      throw new Error(
        `cleanup: ${errors.length} задач(и) упали — тестовые данные могли остаться в БД`,
      )
    }
  }
}
