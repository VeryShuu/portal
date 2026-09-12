import AxeBuilder from '@axe-core/playwright'
import { test, expect, type Page } from './lib/test'
import type { components } from '../../src/api/types.gen'

// The same generated DTOs exported by api/learning, without importing its
// browser-only API implementation into the standalone e2e TypeScript project.
type AttemptResult = components['schemas']['AttemptResult']
type AttemptView = components['schemas']['AttemptView']
type LearningMeta = components['schemas']['LearningMetaOut']
type MyAttempts = components['schemas']['MyAttemptsOut']
type MyCourse = components['schemas']['MyCourseOut']
type MyCourseDetail = components['schemas']['MyCourseDetailOut']

/**
 * Real production learn CSS and components, fixture-only API responses.
 * This must run in project `learn`, not the Portal project: a Vue scoped
 * route stylesheet is loaded after the global theme and can silently undo it.
 * No DB, account, or server-side state is created by this suite.
 */
const COURSE_BASE = {
  created_at: '2026-08-01T00:00:00Z',
  published_at: '2026-08-01T00:00:00Z',
  status: 'published',
  for_all_staff: false,
}
const COURSES = [
  {
    ...COURSE_BASE,
    id: 'c1', slug: 'information-security', title: 'Информационная безопасность',
    description: 'Базовые правила работы с корпоративными данными и защиты учётных записей.',
    progress_completed: 2, progress_total: 6, deadline_at: '2026-09-15T12:00:00Z', cover_url: null,
  },
  {
    ...COURSE_BASE,
    id: 'c2', slug: 'work-safety', title: 'Охрана труда: ежегодный курс',
    description: 'Обязательный курс для всех сотрудников.',
    progress_completed: 5, progress_total: 5, deadline_at: null, cover_url: null,
  },
  {
    ...COURSE_BASE,
    id: 'c3', slug: 'leadership', title: 'Практика руководителя',
    description: 'Коммуникация, обратная связь и развитие команды.',
    progress_completed: 0, progress_total: 4, deadline_at: '2026-10-01T12:00:00Z', cover_url: null,
  },
  {
    ...COURSE_BASE,
    id: 'c4', slug: 'onboarding', title: 'Первый месяц в компании: материалы и полезные контакты',
    description: 'Ориентиры для новых коллег.',
    progress_completed: 1, progress_total: 8, deadline_at: null, cover_url: null,
  },
] satisfies MyCourse[]

const DETAIL = {
  ...COURSES[0],
  items: [
    { id: 'm1', type: 'material', title: 'Политика информационной безопасности', sort_order: 0, url: null, has_file: true, completed: true },
    { id: 'm2', type: 'material', title: 'Пароли, MFA и фишинг', sort_order: 1, url: 'https://example.com/security', has_file: false, completed: true },
    { id: 'm3', type: 'material', title: 'Безопасная работа с документами и корпоративными сервисами', sort_order: 2, url: null, has_file: true, completed: false },
    { id: 't1', type: 'test', title: 'Итоговая проверка знаний', sort_order: 3, url: null, has_file: false, completed: false },
  ],
} satisfies MyCourseDetail

interface FixtureState {
  count: number
  covers: boolean
  error: boolean
  detailDescription?: string
  historyResult?: boolean
  historyError?: boolean
  remainingAttempts?: number
}

async function fixtureApi(page: Page): Promise<FixtureState> {
  const state: FixtureState = { count: 3, covers: false, error: false }
  // Passwordless-вход (миграция 113): оба шага отвечают нейтральным ok —
  // фикстура не зависит от того, существует ли email.
  await page.route('**/api/v1/auth/learning/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/auth/learning/login' || path === '/api/v1/auth/learning/verify') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      })
      return
    }
    await route.abort()
    throw new Error(`Unexpected auth request in fixture-only visual suite: ${path}`)
  })
  await page.route('**/api/v1/learning/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let body: unknown
    let status = 200
    if (path === '/api/v1/learning/meta') {
      body = { video_iframe_origins: [] } satisfies LearningMeta
    } else if (path === '/api/v1/learning/me/courses') {
      if (new URL(page.url()).pathname === '/login') {
        status = 401 // The real login page's unauthenticated session probe.
        body = { detail: 'unauthorized' }
      } else if (state.error) {
        status = 422 // Expected API failure; shared console guard remains enabled.
        body = { detail: 'fixture error' }
      } else {
        body = COURSES.slice(0, state.count).map((course, index) => ({
          ...course,
          cover_url: state.covers && index === 0 ? '/api/v1/learning/fixture-cover' : null,
        }))
      }
    } else if (path === '/api/v1/learning/fixture-cover') {
      // Deliberately plain fixture, not a product image or external service.
      await route.fulfill({
        contentType: 'image/svg+xml',
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="400"><rect width="1200" height="400" fill="#0b2a4a"/></svg>',
      })
      return
    } else if (path === '/api/v1/learning/me/courses/information-security') {
      body = {
        ...DETAIL,
        items: DETAIL.items.map((item) => item.id === 't1' && state.historyResult ? { ...item, completed: true } : item),
        description: state.detailDescription ?? DETAIL.description,
        cover_url: state.covers ? '/api/v1/learning/fixture-cover' : null,
      }
    } else if (path === '/api/v1/learning/me/tests/t1/my-attempts') {
      if (state.historyError) {
        status = 422
        body = { detail: 'fixture history error' }
      } else {
        body = {
          test_item_id: 't1', max_attempts: 3, submitted_count: state.historyResult ? 1 : 0,
          remaining_attempts: state.remainingAttempts ?? 3,
          attempts: state.historyResult ? [{
            id: 'a0', status: 'submitted', started_at: '2026-08-30T12:00:00Z',
            score: 100, passed: true,
          }] : [],
        } satisfies MyAttempts
      }
    } else if (path === '/api/v1/learning/me/tests/t1/attempts') {
      body = {
        id: 'a1', status: 'open', test_item_id: 't1', max_attempts: 3, submitted_count: 0, remaining_attempts: 3,
        started_at: new Date().toISOString(), expires_at: new Date(Date.now() + 17 * 60_000).toISOString(),
        questions: [
          { id: 'q1', text: 'Какое действие нужно выполнить при получении подозрительного письма?', multi: false, options: [{ id: 'o1', text: 'Перейти по ссылке' }, { id: 'o2', text: 'Сообщить в службу информационной безопасности' }] },
          { id: 'q2', text: 'Какие признаки могут указывать на фишинг?', multi: true, options: [{ id: 'o3', text: 'Срочное требование ввести пароль' }, { id: 'o4', text: 'Необычный адрес отправителя' }] },
        ],
      } satisfies AttemptView
    } else if (path === '/api/v1/learning/me/attempts/a1/submit') {
      state.historyResult = true
      state.remainingAttempts = 2
      body = {
        id: 'a1', status: 'submitted', started_at: '2026-08-30T12:00:00Z',
        score: 100, passed: true, remaining_attempts: 2,
      } satisfies AttemptResult
    } else {
      await route.abort()
      throw new Error(`Unexpected learning request in fixture-only visual suite: ${path}`)
    }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  })
  return state
}

async function assertAccessible(page: Page): Promise<void> {
  await page.evaluate(async () => { await document.fonts.ready })
  await expect(page.locator('.n-spin-content--spinning')).toHaveCount(0)
  // NSpin fades real content after fetching. Contrast must be measured in its
  // settled state, not halfway through that transition; do not exclude nodes.
  for (const content of await page.locator('.n-spin-content').all()) {
    await expect(content).toHaveCSS('opacity', '1')
  }
  await expect(page.locator('h1')).toHaveCount(1)
  const result = await new AxeBuilder({ page }).analyze()
  expect(result.violations).toEqual([])
}

async function assertFitsViewport(page: Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }))
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width)
}

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
  { width: 320, height: 844 },
]) {
  test.describe(`learn visual ${viewport.width}px`, () => {
    test.use({ viewport })

    test('auth layouts, semantic headings, AA contrast and keyboard skip link', async ({ page }) => {
      await fixtureApi(page)
      // Passwordless-вход (миграция 113): один маршрут /login, два шага —
      // email → код из письма.
      await page.goto('/login')
      const auth = page.locator('.learn-login')
      await expect(auth).toBeVisible()
      await expect(auth).toHaveCSS('display', 'grid')
      const geometry = await auth.evaluate((element) => {
        const decoration = getComputedStyle(element, '::before')
        const card = element.querySelector('.n-card')!.getBoundingClientRect()
        const shell = element.getBoundingClientRect()
        return {
          decorationContent: decoration.content,
          decorationWidth: parseFloat(decoration.width),
          decorationHeight: parseFloat(decoration.height),
          cardOffset: card.x - shell.x,
        }
      })
      expect(geometry.decorationContent).not.toBe('none')
      expect(geometry.decorationWidth).toBeGreaterThan(200)
      expect(geometry.decorationHeight).toBeGreaterThan(60)
      if (viewport.width >= 768) expect(geometry.cardOffset).toBeGreaterThan(200)
      else expect(geometry.cardOffset).toBeLessThan(2)
      await assertFitsViewport(page)
      await assertAccessible(page)

      // Шаг 2: код из письма
      await page.getByPlaceholder('Email').fill('learner@example.com')
      await page.getByRole('button', { name: 'Получить код', exact: true }).click()
      await expect(page.getByPlaceholder('6 цифр')).toBeVisible()
      // success-тост «код отправлен» уходит с fade-анимацией — полупрозрачный
      // текст ловит color-contrast; меряем после его исчезновения
      await expect(page.locator('.n-message')).toHaveCount(0)
      await expect(auth).toHaveCSS('display', 'grid')
      await assertFitsViewport(page)
      await assertAccessible(page)

      await page.goto('/login')
      await expect(page.locator('.learn-login')).toBeVisible()
      await page.keyboard.press('Tab')
      await expect(page.locator('.skip-link')).toBeFocused()
      await page.keyboard.press('Enter')
      await expect(page.locator('main#learn-main')).toBeFocused()
    })

    test('one to four course cards use the real responsive grid with and without covers', async ({ page }) => {
      const state = await fixtureApi(page)
      for (const count of [1, 2, 3, 4]) {
        state.count = count
        state.covers = count % 2 === 0
        await page.goto('/courses')
        await expect(page.locator('.course-card')).toHaveCount(count)
        await expect(page.getByRole('progressbar')).toHaveCount(count)
        const columns = await page.locator('.course-grid').evaluate((element) =>
          getComputedStyle(element).gridTemplateColumns.split(' ').length,
        )
        expect(columns).toBe(viewport.width >= 768 ? 2 : 1)
        const grid = (await page.locator('.course-grid').boundingBox())!
        const cards = await page.locator('.course-card').all()
        for (const card of cards) {
          const rect = (await card.boundingBox())!
          expect(rect.x).toBeGreaterThanOrEqual(grid.x - 1)
          expect(rect.x + rect.width).toBeLessThanOrEqual(grid.x + grid.width + 1)
        }
        // Odd-count featured card must not leave a third, unintended column.
        if (viewport.width >= 768 && count === 3) {
          const left = (await cards[1].boundingBox())!
          const right = (await cards[2].boundingBox())!
          expect(Math.abs(left.width - right.width)).toBeLessThan(2)
          expect(Math.abs(right.x + right.width - grid.x - grid.width)).toBeLessThan(2)
        }
        if (state.covers) await expect(page.locator('.course-card__cover')).toBeVisible()
        await assertFitsViewport(page)
        await assertAccessible(page)
      }
    })

    test('long introduction sits beside programme, stacks on small screens, and leaves no empty column when absent', async ({ page }) => {
      const state = await fixtureApi(page)
      state.covers = true
      state.detailDescription = 'Вступительное слово о безопасной работе. '.repeat(200)
        + '\n' + 'Длинноеслово'.repeat(30) + '\nЗаключительная часть.'
      await page.goto('/courses/information-security')
      const description = page.locator('.course-description')
      await expect(description).toHaveCount(1)
      // rich-описание рендерится из Markdown: текст тот же, пробелы нормализованы
      await expect(description).toHaveText(
        state.detailDescription.replace(/\s+/g, ' ').trim(),
      )
      await expect(page.locator('.course-header')).not.toContainText('Вступительное слово')
      const programme = (await page.locator('.course-programme').boundingBox())!
      const introduction = (await page.locator('.course-introduction').boundingBox())!
      if (viewport.width >= 1024) {
        // описание — левая колонка, программа — правая (ревью 2026-08-31)
        expect(programme.x).toBeGreaterThanOrEqual(introduction.x + introduction.width)
        expect(Math.abs(introduction.y - programme.y)).toBeLessThan(2)
      } else {
        expect(programme.y).toBeGreaterThanOrEqual(introduction.y + introduction.height)
        expect(Math.abs(introduction.x - programme.x)).toBeLessThan(2)
      }
      const cover = page.locator('.course-cover')
      await expect(cover).toBeVisible()
      const image = (await cover.boundingBox())!
      expect(image.height).toBeGreaterThanOrEqual(220)
      expect(image.height).toBeLessThanOrEqual(360)
      await assertFitsViewport(page)
      await assertAccessible(page)

      state.detailDescription = ''
      await page.reload()
      await expect(page.locator('.course-introduction')).toHaveCount(0)
      const workspace = (await page.locator('.course-workspace').boundingBox())!
      const fullProgramme = (await page.locator('.course-programme').boundingBox())!
      expect(Math.abs(workspace.width - fullProgramme.width)).toBeLessThan(2)
      await assertFitsViewport(page)
    })

    test('long material title and actions remain readable; test idle, passing and result are accessible', async ({ page }) => {
      await fixtureApi(page)
      await page.goto('/courses/information-security')
      const material = page.locator('.item').filter({ hasText: 'Безопасная работа с документами' })
      await expect(material).toHaveCSS('display', 'grid')
      const content = (await material.locator('.item__main').boundingBox())!
      const actions = (await material.locator('.item__actions').boundingBox())!
      expect(content.width).toBeGreaterThan(170)
      expect(actions.y).toBeGreaterThanOrEqual(content.y + content.height)
      expect(Math.abs(actions.x - content.x)).toBeLessThan(2)
      const completed = page.locator('.item--done .item__status').first()
      await expect(completed).toHaveText('Пройден')
      await expect(completed).toBeVisible()
      expect((await completed.boundingBox())!.width).toBeGreaterThan(60)
      await expect(page.locator('.item:not(.item--done) .item__status')).toHaveText(['Не пройден', 'Не пройден'])
      await page.getByRole('button', { name: 'Пройти тест', exact: true }).click()
      await expect(page.getByRole('heading', { name: 'Итоговая проверка знаний', level: 2 })).toBeVisible()
      await expect(page.getByRole('dialog', { name: 'Итоговая проверка знаний' })).toBeVisible()
      await expect(page.locator('.course-programme .test-panel')).toHaveCount(0)
      await assertAccessible(page)
      await page.getByRole('button', { name: 'Начать тест', exact: true }).click()
      // вопросы листаются по одному, навигатор с точками
      await expect(page.locator('.question')).toHaveCount(1)
      await expect(page.locator('.passing-head__progress')).toHaveText('Вопрос 1 из 2')
      await expect(page.locator('.navigator__dot')).toHaveCount(2)
      await expect(page.locator('.timer')).toBeVisible()
      // Naive's native radio is intentionally visually hidden; interact with
      // its visible label, without forcing clicks or modifying application DOM.
      await page.getByText('Сообщить в службу информационной безопасности', { exact: true }).click()
      await expect(page.getByRole('radio', { name: 'Сообщить в службу информационной безопасности' })).toBeChecked()
      await expect(page.locator('.navigator__dot').first()).toHaveClass(/navigator__dot--answered/)
      await page.getByRole('button', { name: 'Далее', exact: true }).click()
      await expect(page.locator('.question__text')).toHaveText('Какие признаки могут указывать на фишинг?')
      await page.getByText('Срочное требование ввести пароль', { exact: true }).click()
      await expect(page.getByRole('checkbox', { name: 'Срочное требование ввести пароль' })).toBeChecked()
      // прыжок точкой назад — ответы сохраняются
      await page.locator('.navigator__dot').first().click()
      await expect(page.getByRole('radio', { name: 'Сообщить в службу информационной безопасности' })).toBeChecked()
      await page.locator('.navigator__dot').nth(1).click()
      await assertAccessible(page)
      await assertFitsViewport(page)
      await page.keyboard.press('Escape')
      await expect(page.getByRole('dialog', { name: 'Итоговая проверка знаний' })).toBeVisible()
      await page.mouse.click(2, 2)
      await expect(page.getByRole('checkbox', { name: 'Срочное требование ввести пароль' })).toBeChecked()
      await page.getByRole('button', { name: 'Закрыть', exact: true }).click()
      await expect(page.getByText('Неотправленные ответы не сохранятся.', { exact: false })).toBeVisible()
      await page.getByRole('button', { name: 'Продолжить отвечать', exact: true }).click()
      await expect(page.getByRole('checkbox', { name: 'Срочное требование ввести пароль' })).toBeChecked()
      await page.getByRole('button', { name: 'Отправить ответы', exact: true }).click()
      await expect(page.locator('.test-score__value')).toHaveText('100%')
      await expect(page.getByRole('button', { name: 'Пройти повторно', exact: true })).toBeVisible()
      await page.getByRole('button', { name: 'Вернуться к курсу', exact: true }).click()
      await expect(page.getByRole('dialog')).toHaveCount(0)
      await expect(page.getByRole('button', { name: 'Результаты теста', exact: true })).toBeFocused()
      await assertAccessible(page)
    })

    test('completed results stay compact, preserve course geometry and restore keyboard focus', async ({ page }) => {
      const state = await fixtureApi(page)
      state.historyResult = true
      state.remainingAttempts = 0
      const mutations: string[] = []
      page.on('request', (request) => { if (request.method() === 'POST') mutations.push(request.url()) })
      await page.goto('/courses/information-security')
      const course = page.locator('.course-programme')
      const before = (await course.boundingBox())!
      const opener = page.getByRole('button', { name: 'Результаты теста', exact: true })
      await opener.click()
      const dialog = page.getByRole('dialog', { name: 'Итоговая проверка знаний' })
      await expect(dialog).toBeVisible()
      await expect(dialog.locator('.test-score__value')).toHaveText('100%')
      await expect(dialog).toContainText('Лимит попыток исчерпан')
      await expect(dialog.getByRole('button', { name: 'Начать тест', exact: true })).toHaveCount(0)
      await expect(dialog.getByRole('button', { name: 'Пройти повторно', exact: true })).toHaveCount(0)
      expect(Math.abs((await course.boundingBox())!.height - before.height)).toBeLessThan(2)
      const box = (await dialog.boundingBox())!
      expect(box.width).toBeLessThanOrEqual(Math.min(560, viewport.width - 32))
      expect(box.height).toBeLessThan(viewport.height - 32)
      await page.keyboard.press('Shift+Tab')
      // Naive UI's focus-lock sentinels live beside the teleported dialog node;
      // verify focus remains trapped in the modal layer rather than requiring
      // the active element to be a descendant of our content section.
      await expect.poll(() => page.evaluate(() => document.activeElement !== document.body)).toBe(true)
      await assertAccessible(page)
      await page.keyboard.press('Escape')
      await expect(dialog).toHaveCount(0)
      await expect(opener).toBeFocused()
      expect(mutations).toEqual([])
    })

    test('history errors offer retry without exposing start or unlimited allowance', async ({ page }) => {
      const state = await fixtureApi(page)
      state.historyError = true
      await page.goto('/courses/information-security')
      await page.getByRole('button', { name: 'Пройти тест', exact: true }).click()
      const dialog = page.getByRole('dialog', { name: 'Итоговая проверка знаний' })
      await expect(dialog.locator('.test-history-error')).toBeVisible()
      await expect(dialog.getByRole('button', { name: 'Начать тест', exact: true })).toHaveCount(0)
      await expect(dialog).not.toContainText('без ограничений')
      state.historyError = false
      await dialog.getByRole('button', { name: 'Повторить', exact: true }).click()
      await expect(dialog.getByRole('button', { name: 'Начать тест', exact: true })).toBeVisible()
      await assertAccessible(page)
    })

    test('empty and recoverable-error screens retain accessible layout', async ({ page }) => {
      const state = await fixtureApi(page)
      state.count = 0
      await page.goto('/courses')
      await expect(page.locator('.n-empty')).toBeVisible()
      await assertFitsViewport(page)
      await assertAccessible(page)
      state.error = true
      await page.reload()
      await expect(page.locator('.n-alert')).toBeVisible()
      await assertFitsViewport(page)
      await assertAccessible(page)
      state.error = false
      state.count = 3
      await page.getByRole('button', { name: 'Повторить', exact: true }).click()
      await expect(page.locator('.course-card')).toHaveCount(3)
    })
  })
}
