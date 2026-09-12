import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'

/**
 * Learn-шелл и роутер на РЕАЛЬНЫХ модулях: createLearnRouter (маршруты,
 * имена совпадают с портал-роутером для переиспользуемых страниц) и
 * LearnApp (брендинг, кнопка «Выйти» только за сессией).
 */

const mocks = vi.hoisted(() => ({
  authApi: {
    learnerLogout: vi.fn(),
  },
}))

vi.mock('../../src/api/learningAuth', () => mocks.authApi)
// Гость по умолчанию: проба onMounted на логине получает 401 и остаётся.
// Отдельные тесты перекрывают через fetchMyCoursesMock.
const fetchMyCoursesMock = vi.fn().mockRejectedValue({ status: 401 })
vi.mock('../../src/api/learning', () => ({
  fetchMyCourses: (...a: unknown[]) => fetchMyCoursesMock(...(a as [])),
}))

// Частичный мок naive-ui: провайдеры и базовые контролы — стабы, остальное
// (используется переиспользуемыми портал-страницами курса) — реальный модуль.
vi.mock('naive-ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('naive-ui')>()
  return {
    ...actual,
    NMessageProvider: { template: '<div><slot /></div>' },
    NDialogProvider: { template: '<div><slot /></div>' },
    NNotificationProvider: { template: '<div><slot /></div>' },
    NButton: {
      template:
        '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
      props: ['disabled', 'loading', 'quaternary', 'secondary', 'type', 'size', 'block'],
      emits: ['click'],
    },
    NIcon: { template: '<i><slot /></i>' },
    useMessage: () => ({ success: vi.fn(), error: vi.fn() }),
  }
})

import LearnApp from '../../src/learn/LearnApp.vue'
import { createLearnRouter } from '../../src/learn/router'

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'ru',
    missingWarn: false,
    fallbackWarn: false,
    messages: {
      ru: {
        learning: {
          learn: { brand: 'Обучение', logout: 'Выйти' },
          page: { title: 'Обучение' },
        },
      },
    },
  })
}

async function mountApp(path: string) {
  const router = createLearnRouter()
  await router.push(path)
  await router.isReady()
  const w = mount(LearnApp, {
    global: {
      plugins: [router, makeI18n(), [VueQueryPlugin, { queryClient: new QueryClient({}) }]],
    },
  })
  await flushPromises()
  return w
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('createLearnRouter', () => {
  it('имена страниц курса совпадают с портал-роутером', () => {
    const router = createLearnRouter()
    expect(router.resolve({ name: 'learning' }).path).toBe('/courses')
    expect(router.resolve({ name: 'learning-course', params: { slug: 'x' } }).path).toBe(
      '/courses/x',
    )
  })

  it('корень и неизвестные пути ведут на курсы', () => {
    const router = createLearnRouter()
    expect(router.resolve('/').matched.at(-1)!.name).toBeUndefined() // redirect-запись
    const loaders = router.getRoutes().map((r) => r.components?.default)
    expect(loaders.some(Boolean)).toBe(true)
  })

  it('старые парольные маршруты (/forgot, /reset, /reset-password) ведут на вход (passwordless)', async () => {
    // Письма восстановления и формы смены пароля упразднены (миграция 113):
    // старые ссылки не должны отдавать 404 — уводим на форму входа.
    const router = createLearnRouter()
    await router.push('/reset-password?token=abc123')
    await router.isReady()
    expect(router.currentRoute.value.name).toBe('learn-login')

    await router.push('/forgot')
    expect(router.currentRoute.value.name).toBe('learn-login')

    await router.push('/reset')
    expect(router.currentRoute.value.name).toBe('learn-login')
  })

  it('ленивые загрузчики маршрутов работают', async () => {
    const router = createLearnRouter()
    for (const record of router.getRoutes()) {
      const comp = record.components?.default as (() => Promise<unknown>) | undefined
      if (typeof comp === 'function' && record.name) {
        expect(await comp()).toBeTruthy()
      }
    }
  })
})

describe('LearnApp', () => {
  it('на логине нет кнопки «Выйти», бренд присутствует', async () => {
    const w = await mountApp('/login')
    expect(w.text()).toContain('Обучение')
    expect(w.findAll('button.n-button').some((b) => b.text().includes('Выйти'))).toBe(false)
    expect(w.find('.skip-link').attributes('href')).toBe('#learn-main')
    expect(w.find('main#learn-main').attributes('tabindex')).toBe('-1')
    expect(w.find('.learn-shell__brand-mark').attributes('aria-hidden')).toBe('true')
  })

  it('залогиненный на логине автоматически уходит на курсы', async () => {
    fetchMyCoursesMock.mockResolvedValueOnce([])
    const w = await mountApp('/login')
    await flushPromises()
    // probe прошёл → страница покинула логин (redirect на /courses)
    expect(w.find('button.n-button').exists()).toBe(true)
  })

  it('на курсах кнопка «Выйти» есть и вызывает logout → логин', async () => {
    const w = await mountApp('/courses')
    await flushPromises()
    const logout = w.findAll('button.n-button').find((b) => b.text().includes('Выйти'))
    expect(logout).toBeTruthy()
    mocks.authApi.learnerLogout.mockResolvedValueOnce({ ok: true })
    await logout!.trigger('click')
    await flushPromises()
    expect(mocks.authApi.learnerLogout).toHaveBeenCalled()
  })
})
