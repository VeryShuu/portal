import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import { ref } from 'vue'

/**
 * Характеризующий тест виджета «Мои курсы» (главная страница).
 *
 * Контракты:
 * - скрыт целиком, когда модуль learning выключен (v-if на корне)
 * - рамка виджета — те же классы .widget/.widget__header/.widget__title, что
 *   у соседей (стили дублируются в scoped-стилях каждого виджета)
 * - в шапке ссылка «Все курсы» → /learning
 * - показывает ТОЛЬКО незавершённые курсы (пройденный = completed>=total,
 *   та же семантика, что на странице «Обучение»)
 * - если все назначенные курсы пройдены — отдельный empty-state «allDone»
 * - процент прогресса = round(completed/total*100)
 * - показывает empty-state, когда список курсов пуст
 */

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    ru: {
      learning: {
        widget: {
          title: 'Мои курсы',
          viewAll: 'Все курсы',
          empty: 'Вы пока не записаны ни на один курс',
          allDone: 'Все назначенные курсы пройдены',
        },
      },
    },
  },
})

const mockApi = vi.fn()
vi.mock('../../src/api/index', () => ({
  api: mockApi,
  apiUpload: vi.fn(),
  BASE_URL: '/api/v1',
}))

// строки курсов стали ссылками на карточку курса (learner-страницы);
// :href вместо атрибута to — props мок-компонента не попадают в DOM
vi.mock('vue-router', () => ({
  RouterLink: {
    props: ['to'],
    template: '<a class="router-link" :href="to"><slot /></a>',
  },
}))

let moduleEnabled = true
vi.mock('../../src/stores/modules', () => ({
  useModulesStore: () => ({ isEnabled: () => moduleEnabled }),
}))

let mockLoading = false
const mockData = ref<any[] | undefined>(undefined)
vi.mock('../../src/queries/learning', () => ({
  useMyCoursesQuery: () => ({ data: mockData, isLoading: ref(mockLoading) }),
}))

import MyCoursesWidget from '../../src/components/widgets/MyCoursesWidget.vue'

describe('MyCoursesWidget', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    moduleEnabled = true
    mockLoading = false
    mockData.value = undefined
  })

  it('renders course title and completed/total counter', async () => {
    mockData.value = [
      { id: 'c1', slug: 'a', title: 'Охрана труда', progress_completed: 1, progress_total: 4 },
    ]
    const w = mount(MyCoursesWidget, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.text()).toContain('Охрана труда')
    expect(w.text()).toContain('1/4')
    const bar = w.find('.n-progress')
    expect(bar.exists()).toBe(true)
  })

  it('exposes full course title as native tooltip on the truncated link', async () => {
    const longTitle = 'Программа первичного (повторного) инструктажа по пожарной безопасности'
    mockData.value = [
      { id: 'c1', slug: 'a', title: longTitle, progress_completed: 0, progress_total: 10 },
    ]
    const w = mount(MyCoursesWidget, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.find('.my-courses__link').attributes('title')).toBe(longTitle)
  })

  it('shows empty state when no courses', async () => {
    mockData.value = []
    const w = mount(MyCoursesWidget, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.text()).toContain('Вы пока не записаны ни на один курс')
  })

  it('shows skeleton while loading', async () => {
    mockLoading = true
    const w = mount(MyCoursesWidget, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.findAll('.my-courses__skeleton-row').length).toBe(2)
  })

  it('hidden entirely when learning module disabled', async () => {
    moduleEnabled = false
    mockData.value = [{ id: 'c1', slug: 'a', title: 'X', progress_completed: 0, progress_total: 2 }]
    const w = mount(MyCoursesWidget, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.find('section.widget').exists()).toBe(false)
  })

  it('shows header link «Все курсы» to /learning', async () => {
    mockData.value = [{ id: 'c1', slug: 'a', title: 'Охрана труда', progress_completed: 1, progress_total: 4 }]
    const w = mount(MyCoursesWidget, { global: { plugins: [i18n] } })
    await flushPromises()
    const link = w.find('.widget__link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('/learning')
  })

  it('hides completed course, shows only in-progress ones', async () => {
    mockData.value = [
      { id: 'c1', slug: 'done', title: 'Пройденный курс', progress_completed: 3, progress_total: 3 },
      { id: 'c2', slug: 'wip', title: 'Охрана труда', progress_completed: 1, progress_total: 4 },
    ]
    const w = mount(MyCoursesWidget, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.text()).toContain('Охрана труда')
    expect(w.text()).not.toContain('Пройденный курс')
    expect(w.findAll('.my-courses__item').length).toBe(1)
  })

  it('shows allDone state when every course is completed', async () => {
    mockData.value = [
      { id: 'c1', slug: 'done', title: 'Пройденный курс', progress_completed: 3, progress_total: 3 },
    ]
    const w = mount(MyCoursesWidget, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.text()).toContain('Все назначенные курсы пройдены')
    expect(w.text()).not.toContain('Вы пока не записаны ни на один курс')
  })

  it('treats course without items (total=0) as not completed', async () => {
    mockData.value = [{ id: 'c1', slug: 'empty', title: 'Пустой курс', progress_completed: 0, progress_total: 0 }]
    const w = mount(MyCoursesWidget, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.text()).toContain('Пустой курс')
  })
})
