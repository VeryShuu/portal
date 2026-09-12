import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, ref, watch } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'

/**
 * Learner-раздел «Обучение» (портал): api-мэппинг, страница списка курсов,
 * карточка курса и тест-раннер (старт/продолжение/отправка попытки).
 */

const mockApi = vi.fn()
const mockApiUpload = vi.fn()
const mockDialogWarning = vi.fn()

vi.mock('../../src/api/index', () => ({
  api: mockApi,
  apiUpload: mockApiUpload,
  BASE_URL: '/api/v1',
}))

vi.mock('vue-router', () => ({
  RouterLink: defineComponent({ props: ['to'], template: '<a class="router-link"><slot /></a>' }),
  useRoute: () => ({ params: { slug: 'kurs-1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: ref('ru') }),
}))

vi.mock('naive-ui', () => {
  const NButton = defineComponent({
    props: { disabled: { type: Boolean, default: false }, tag: String, href: String },
    template: `<component
      :is="tag === 'a' ? 'a' : 'button'"
      class="n-button"
      :disabled="disabled"
      :href="href"
      @click="$emit('click')"
    ><slot /></component>`,
  })
  return {
    NButton,
    NModal: defineComponent({
      props: ['show', 'maskClosable', 'closeOnEsc'],
      emits: ['after-leave', 'update:show'],
      setup(props, { emit }) {
        watch(() => props.show, (show) => { if (!show) emit('after-leave') })
        return {}
      },
      template: '<div v-if="show" class="n-modal"><slot /></div>',
    }),
    useDialog: () => ({ warning: mockDialogWarning }),
    NSpin: defineComponent({ props: ['show'], template: '<div class="n-spin"><slot /></div>' }),
    NIcon: defineComponent({ props: ['size', 'color'], template: '<span class="n-icon"><slot /></span>' }),
    NEmpty: defineComponent({ props: ['description'], template: '<div class="n-empty">{{ description }}</div>' }),
    NProgress: defineComponent({ props: ['percentage', 'height', 'showIndicator', 'type'], template: '<div class="n-progress" />' }),
    NTag: defineComponent({ props: ['type', 'size', 'bordered'], template: '<span class="n-tag"><slot /></span>' }),
    NCard: defineComponent({
      props: ['title', 'bordered'],
      template: '<div class="n-card"><h3>{{ title }}</h3><slot name="header-extra" /><slot /></div>',
    }),
    NAlert: defineComponent({ props: ['type', 'showIcon'], template: '<div class="n-alert"><slot /></div>' }),
    NResult: defineComponent({ props: ['status', 'title', 'description'], template: '<div class="n-result">{{ title }} {{ description }}</div>' }),
    NCheckboxGroup: defineComponent({
      props: ['value'],
      emits: ['update:value'],
      template: '<div class="n-checkbox-group" @click="$emit(\'update:value\', [\'opt1\'])"><slot /></div>',
    }),
    NCheckbox: defineComponent({
      props: {
        value: { type: [Boolean, String], default: false },
        checked: { type: Boolean, default: false },
        label: String,
      },
      emits: ['update:checked'],
      template:
        '<label class="n-checkbox" @click="$emit(\'update:checked\', !checked)"><slot />{{ label }}</label>',
    }),
    NRadioGroup: defineComponent({
      props: ['value'],
      emits: ['update:value'],
      template: '<div class="n-radio-group" @click="$emit(\'update:value\', \'opt2\')"><slot /></div>',
    }),
    NRadio: defineComponent({ props: ['value'], template: '<label class="n-radio"><slot /></label>' }),
    useMessage: () => ({ success: vi.fn(), error: vi.fn() }),
  }
})

const COURSE = {
  id: 'c1',
  slug: 'kurs-1',
  title: 'Охрана труда',
  description: 'Базовый курс',
  status: 'published',
  published_at: null,
  created_at: '2026-08-01T00:00:00Z',
  progress_completed: 1,
  progress_total: 2,
  items: [
    { id: 'm1', type: 'material', title: 'Инструкция', sort_order: 0, url: null, has_file: true, completed: false },
    { id: 't1', type: 'test', title: 'Тест итоговый', sort_order: 1, url: null, has_file: false, completed: false },
  ],
}

const ATTEMPT_VIEW = {
  id: 'a1',
  status: 'open',
  test_item_id: 't1',
  questions: [
    { id: 'q1', text: 'Вопрос 1', multi: true, options: [{ id: 'opt1', text: 'Вариант' }] },
  ],
  max_attempts: 3,
  submitted_count: 0,
  remaining_attempts: 3,
  started_at: '2026-08-28T00:00:00Z',
}

const ATTEMPT_RESULT = {
  id: 'a1',
  status: 'submitted',
  score: 100,
  passed: true,
  remaining_attempts: 2,
  started_at: '2026-08-28T00:00:00Z',
  submitted_at: '2026-08-28T00:05:00Z',
}

function mountWith(component: unknown, opts: { props?: Record<string, unknown> } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return mount(component as object, {
    props: opts.props,
    global: { plugins: [[VueQueryPlugin, { queryClient: qc }]] as never[] },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('learner api mapping', () => {
  beforeEach(() => {
    mockApi.mockReset()
    mockApi.mockResolvedValue({})
  })

  it('fetchMyCourse / fetchMyAttempts / fetchAttempt GET-ят свои пути', async () => {
    const api = await import('../../src/api/learning')
    await api.fetchMyCourse('kurs-1')
    expect(mockApi).toHaveBeenCalledWith('/learning/me/courses/kurs-1')
    await api.fetchMyAttempts('t1')
    expect(mockApi).toHaveBeenCalledWith('/learning/me/tests/t1/my-attempts')
    await api.fetchAttempt('a1')
    expect(mockApi).toHaveBeenCalledWith('/learning/me/attempts/a1')
  })

  it('startAttempt / completeMaterial POST-ят, submitAttempt передаёт answers', async () => {
    const api = await import('../../src/api/learning')
    await api.startAttempt('t1')
    expect(mockApi).toHaveBeenCalledWith('/learning/me/tests/t1/attempts', { method: 'POST' })
    await api.completeMaterial('m1')
    expect(mockApi).toHaveBeenCalledWith('/learning/me/items/m1/complete', { method: 'POST' })
    await api.submitAttempt('a1', { q1: ['opt1'] })
    expect(mockApi).toHaveBeenCalledWith('/learning/me/attempts/a1/submit', {
      method: 'POST',
      body: { answers: { q1: ['opt1'] } },
    })
  })

  it('materialFileUrl строит ссылку стриминга', async () => {
    const { materialFileUrl } = await import('../../src/api/learning')
    expect(materialFileUrl('m1')).toBe('/api/v1/learning/me/items/m1/file')
  })
})

describe('LearningPage', () => {
  it('рисует курсы с прогрессом и ссылками на карточку', async () => {
    mockApi.mockResolvedValue([COURSE])
    const { default: LearningPage } = await import('../../src/pages/learning/LearningPage.vue')
    const w = mountWith(LearningPage)
    await flushPromises()
    expect(w.text()).toContain('Охрана труда')
    expect(w.text()).toContain('learning.page.progress')
    expect(w.findAll('.router-link').length).toBeGreaterThan(0)
  })

  it('обложка курса рендерится в карточке, alt = название', async () => {
    mockApi.mockResolvedValue([{ ...COURSE, cover_url: '/api/v1/learning/me/courses/kurs-1/cover?v=1' }])
    const { default: LearningPage } = await import('../../src/pages/learning/LearningPage.vue')
    const w = mountWith(LearningPage)
    await flushPromises()
    const img = w.find('img.course-card__cover')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('/api/v1/learning/me/courses/kurs-1/cover?v=1')
    expect(img.attributes('alt')).toBe('Охрана труда')
  })

  it('дедлайн курса отображается в карточке', async () => {
    mockApi.mockResolvedValue([
      { ...COURSE, deadline_at: '2026-09-15T00:00:00Z' },
    ])
    const { default: LearningPage } = await import('../../src/pages/learning/LearningPage.vue')
    const w = mountWith(LearningPage)
    await flushPromises()
    expect(w.text()).toContain('learning.page.deadline')
    expect(w.find('.course-card__deadline').exists()).toBe(true)
  })

  it('без cover_url карточка обходится без картинки', async () => {
    mockApi.mockResolvedValue([COURSE])
    const { default: LearningPage } = await import('../../src/pages/learning/LearningPage.vue')
    const w = mountWith(LearningPage)
    await flushPromises()
    expect(w.find('img.course-card__cover').exists()).toBe(false)
  })

  it('ошибка загрузки — error-state с повтором, не «нет курсов» (ревью P3)', async () => {
    mockApi.mockRejectedValue({ status: 500 })
    const { default: LearningPage } = await import('../../src/pages/learning/LearningPage.vue')
    const w = mountWith(LearningPage)
    await flushPromises()
    expect(w.find('.n-empty').exists()).toBe(false)
    expect(w.find('.n-alert').exists()).toBe(true)
    const callsAfterError = mockApi.mock.calls.length

    const retry = w.findAll('button').find((b) => b.text().includes('learning.page.retry'))!
    expect(retry).toBeTruthy()
    mockApi.mockResolvedValueOnce([COURSE])
    await retry.trigger('click')
    await flushPromises()
    expect(mockApi.mock.calls.length).toBeGreaterThan(callsAfterError)
  })

  it('пустой список — empty state', async () => {
    mockApi.mockResolvedValue([])
    const { default: LearningPage } = await import('../../src/pages/learning/LearningPage.vue')
    const w = mountWith(LearningPage)
    await flushPromises()
    expect(w.find('.n-empty').exists()).toBe(true)
  })

  it('курсы сгруппированы по категориям по sort_order, без категории — в конце', async () => {
    mockApi.mockResolvedValue([
      { ...COURSE, id: 'c1', title: 'Курс А', category_title: 'Инструктажи', category_sort: 1 },
      { ...COURSE, id: 'c2', title: 'Курс Б', category_title: 'ГО и ЧС', category_sort: 0 },
      { ...COURSE, id: 'c3', title: 'Курс В' },
    ])
    const { default: LearningPage } = await import('../../src/pages/learning/LearningPage.vue')
    const w = mountWith(LearningPage)
    await flushPromises()
    const titles = w.findAll('.course-block__title').map((h) => h.text())
    expect(titles).toEqual(['ГО и ЧС', 'Инструктажи', 'learning.page.otherCourses'])
    // курс без категории — в последнем блоке
    const blocks = w.findAll('.course-block')
    expect(blocks[blocks.length - 1].text()).toContain('Курс В')
  })

  it('пройденный курс — в конце блока и приглушён (прозрачность)', async () => {
    localStorage.removeItem('learning.hideCompleted')
    mockApi.mockResolvedValue([
      { ...COURSE, id: 'c1', title: 'Пройденный', progress_completed: 2, progress_total: 2 },
      { ...COURSE, id: 'c2', title: 'Активный', progress_completed: 0, progress_total: 2 },
    ])
    const { default: LearningPage } = await import('../../src/pages/learning/LearningPage.vue')
    const w = mountWith(LearningPage)
    await flushPromises()
    const cards = w.findAll('.course-card')
    expect(cards.map((c) => c.text())).toEqual([
      expect.stringContaining('Активный'),
      expect.stringContaining('Пройденный'),
    ])
    expect(cards[1].classes()).toContain('course-card--done')
    expect(cards[0].classes()).not.toContain('course-card--done')
  })

  it('чекбокс «скрыть пройденные» убирает их со страницы', async () => {
    localStorage.removeItem('learning.hideCompleted')
    mockApi.mockResolvedValue([
      { ...COURSE, id: 'c1', title: 'Пройденный', progress_completed: 2, progress_total: 2 },
      { ...COURSE, id: 'c2', title: 'Активный', progress_completed: 1, progress_total: 2 },
    ])
    const { default: LearningPage } = await import('../../src/pages/learning/LearningPage.vue')
    const w = mountWith(LearningPage)
    await flushPromises()
    expect(w.text()).toContain('Пройденный')

    await w.find('.n-checkbox').trigger('click')
    await flushPromises()
    expect(w.text()).not.toContain('Пройденный')
    expect(w.text()).toContain('Активный')
    expect(localStorage.getItem('learning.hideCompleted')).toBe('1')
  })

  it('чекбокса нет, пока пройденных курсов нет', async () => {
    localStorage.removeItem('learning.hideCompleted')
    mockApi.mockResolvedValue([COURSE])
    const { default: LearningPage } = await import('../../src/pages/learning/LearningPage.vue')
    const w = mountWith(LearningPage)
    await flushPromises()
    expect(w.find('.n-checkbox').exists()).toBe(false)
  })

  it('все курсы пройдены и скрыты — empty state, а не пустая страница', async () => {
    localStorage.removeItem('learning.hideCompleted')
    mockApi.mockResolvedValue([
      { ...COURSE, id: 'c1', title: 'Пройденный', progress_completed: 2, progress_total: 2 },
    ])
    const { default: LearningPage } = await import('../../src/pages/learning/LearningPage.vue')
    const w = mountWith(LearningPage)
    await flushPromises()
    await w.find('.n-checkbox').trigger('click')
    await flushPromises()
    expect(w.find('.n-empty').exists()).toBe(true)
  })
})

describe('LearnerCoursePage', () => {
  it('рисует элементы курса; PDF-ссылка и отметка ознакомления', async () => {
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/courses/kurs-1') return Promise.resolve(COURSE)
      if (url === '/learning/me/items/m1/complete') return Promise.resolve({ completed: true })
      return Promise.resolve({})
    })
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()
    expect(w.text()).toContain('Инструкция')
    expect(w.text()).toContain('Тест итоговый')

    const pdf = w.findAll('a').find((a) => a.attributes('href')?.includes('/items/m1/file'))
    expect(pdf).toBeDefined()

    const doneBtn = w.findAll('button').find((b) => b.text().includes('learning.course.markDone'))!
    await doneBtn.trigger('click')
    await flushPromises()
    expect(mockApi).toHaveBeenCalledWith('/learning/me/items/m1/complete', { method: 'POST' })
  })

  it('раздел-заголовок рендерится структурой, нумерация элементов сквозная', async () => {
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/courses/kurs-1') {
        return Promise.resolve({
          ...COURSE,
          items: [
            { id: 'm1', type: 'material', title: 'Инструкция', sort_order: 0, url: null, has_file: true, completed: false },
            { id: 's1', type: 'section', title: 'Инструкции', sort_order: 1, url: null, has_file: false, completed: false },
            { id: 't1', type: 'test', title: 'Тест итоговый', sort_order: 2, url: null, has_file: false, completed: false },
          ],
        })
      }
      return Promise.resolve({})
    })
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()
    const sections = w.findAll('.items__section')
    expect(sections.length).toBe(1)
    expect(sections[0].text()).toContain('Инструкции')
    // сквозная нумерация: материал = 01, тест = 02 (раздел не нумеруется)
    const numbers = w.findAll('.item__number').map((x) => x.text())
    expect(numbers).toEqual(['01', '02'])
  })

  it('дедлайн в шапке страницы курса', async () => {
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/courses/kurs-1') {
        return Promise.resolve({ ...COURSE, deadline_at: '2026-09-15T00:00:00Z' })
      }
      return Promise.resolve({})
    })
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()
    expect(w.find('.course-deadline').exists()).toBe(true)
  })

  it('завершённый материал показывает статус и не предлагает повторную отметку', async () => {
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/courses/kurs-1') {
        return Promise.resolve({ ...COURSE, items: [{ ...COURSE.items[0], completed: true }] })
      }
      return Promise.resolve({})
    })
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()
    expect(w.find('.item__status').text()).toBe('learning.page.done')
    expect(w.find('.item__status .n-icon').attributes('aria-hidden')).toBe('true')
    expect(w.find('.item--done').exists()).toBe(true)
    expect(w.text()).not.toContain('learning.course.markDone')
  })

  it.each([0, 1, 2])('прогресс %i из 2: статусы материалов и тестов совпадают с доступными действиями', async (done) => {
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/courses/kurs-1') {
        return Promise.resolve({
          ...COURSE,
          progress_completed: done,
          items: COURSE.items.map((item, index) => ({ ...item, completed: index < done })),
        })
      }
      return Promise.resolve({})
    })
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()
    expect(w.find('.course-percentage').text()).toBe(`${done * 50}%`)
    expect(w.findAll('.item--done')).toHaveLength(done)
    const statuses = w.findAll('.item__status').map((status) => status.text())
    expect(statuses.filter((status) => status === 'learning.page.done')).toHaveLength(done)
    expect(statuses.filter((status) => status === 'learning.course.notCompleted')).toHaveLength(2 - done)
    expect(w.text().includes('learning.course.markDone')).toBe(done === 0)
    expect(w.text().includes('learning.course.takeTest')).toBe(done < 2)
    expect(w.text().includes('learning.course.testResults')).toBe(done === 2)
    expect(w.findAll('a').some((a) => a.text() === 'learning.course.certificate')).toBe(done === 2)
  })

  it('результаты завершённого теста открывают историю, не расходуя новую попытку', async () => {
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/courses/kurs-1') {
        return Promise.resolve({ ...COURSE, items: [{ ...COURSE.items[1], completed: true }] })
      }
      if (url === '/learning/me/tests/t1/my-attempts') {
        return Promise.resolve({
          test_item_id: 't1', max_attempts: 3, submitted_count: 1, remaining_attempts: 2,
          attempts: [ATTEMPT_RESULT],
        })
      }
      return Promise.resolve({})
    })
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()
    const results = w.findAll('button').find((button) => button.text() === 'learning.course.testResults')!
    expect(results).toBeDefined()
    await results.trigger('click')
    await flushPromises()
    const panel = w.find('.test-panel')
    expect(w.find('.course-programme .test-panel').exists()).toBe(false)
    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain('learning.test.passed')
    expect(panel.text()).toContain('learning.test.repeat')
    expect(mockApi).toHaveBeenCalledWith('/learning/me/tests/t1/my-attempts')
    expect(mockApi).not.toHaveBeenCalledWith('/learning/me/tests/t1/attempts', expect.anything())
  })

  it('длинное вступление: rich-рендер целиком, раздел — левой колонкой (ревью 2026-08-31)', async () => {
    const description = 'Вступительное слово. '.repeat(400) + '\nВторая часть вступления.'
    mockApi.mockImplementation((url: string) => Promise.resolve(
      url === '/learning/me/courses/kurs-1' ? { ...COURSE, description } : {},
    ))
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()
    expect(w.find('.course-header').text()).not.toContain('Вступительное слово')
    expect(w.findAll('.course-description')).toHaveLength(1)
    const desc = w.find('.course-introduction .course-description')
    expect(desc.text()).toContain('Вступительное слово.')
    expect(desc.text()).toContain('Вторая часть вступления.')
    // описание — левая колонка, программа — правая: порядок секций в DOM
    const introduction = w.find('.course-introduction').element
    expect(introduction.nextElementSibling).toBe(w.find('.course-programme').element)
    expect(w.find('.course-workspace--with-description').exists()).toBe(true)
  })

  it('rich-описание: опасный HTML вычищается при рендере (v-html под защитой)', async () => {
    mockApi.mockImplementation((url: string) => Promise.resolve(
      url === '/learning/me/courses/kurs-1'
        ? { ...COURSE, description: '<p>Безопасно <script>alert(1)</script><strong>текст</strong></p>' }
        : {},
    ))
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()
    const desc = w.find('.course-description')
    expect(desc.text()).toContain('Безопасно')
    expect(desc.text()).toContain('текст')
    expect(w.find('.course-description script').exists()).toBe(false)
    expect(desc.html()).not.toContain('alert(1)')
  })

  it.each(['', '   \n '])('без описания нет пустой колонки (%j)', async (description) => {
    mockApi.mockImplementation((url: string) => Promise.resolve(
      url === '/learning/me/courses/kurs-1' ? { ...COURSE, description } : {},
    ))
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()
    expect(w.find('.course-introduction').exists()).toBe(false)
    expect(w.find('.course-workspace--with-description').exists()).toBe(false)
    expect(w.findAll('.items .item')).toHaveLength(2)
  })

  it('пустой курс не считается пройденным, вступление остаётся доступно', async () => {
    mockApi.mockImplementation((url: string) => Promise.resolve(
      url === '/learning/me/courses/kurs-1'
        ? { ...COURSE, items: [], progress_completed: 0, progress_total: 0 } : {},
    ))
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()
    expect(w.find('.n-empty').exists()).toBe(true)
    expect(w.find('.course-description').text()).toBe(COURSE.description)
    expect(w.find('.course-percentage').text()).toBe('0%')
    expect(w.text()).not.toContain('learning.course.certificate')
  })

  it('баннер обложки над заголовком, если cover_url задан', async () => {
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/courses/kurs-1') {
        return Promise.resolve({
          ...COURSE,
          cover_url: '/api/v1/learning/me/courses/kurs-1/cover?v=2',
        })
      }
      return Promise.resolve({})
    })
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()
    const img = w.find('img.course-cover')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('/api/v1/learning/me/courses/kurs-1/cover?v=2')
  })

  it('видео-материал: плеер встроен сразу (как в новостях), внешняя ссылка сохранена', async () => {
    const courseWithVideo = {
      ...COURSE,
      items: [
        {
          id: 'v1',
          type: 'material',
          title: 'Вебинар',
          sort_order: 0,
          url: 'https://rutube.ru/video/abc123def0/',
          has_file: false,
          completed: false,
        },
        {
          id: 'w1',
          type: 'material',
          title: 'Внешний регламент',
          sort_order: 1,
          url: 'https://example.com/guide',
          has_file: false,
          completed: false,
        },
        ...COURSE.items,
      ],
    }
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/courses/kurs-1') return Promise.resolve(courseWithVideo)
      return Promise.resolve({})
    })
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()

    // видео-материал получил iframe с embed-URL сразу, без клика
    const iframe = w.find('iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toBe('https://rutube.ru/play/embed/abc123def0')
    // не-видео ссылка плеера не получила — iframe ровно один
    expect(w.findAll('iframe').length).toBe(1)

    // исходная ссылка осталась доступной («открыть в новой вкладке»)
    const link = w
      .findAll('a')
      .find((a) => a.attributes('href') === 'https://rutube.ru/video/abc123def0/')
    expect(link).toBeDefined()
    expect(link!.attributes('rel')).toBe('noopener')
  })
})

describe('LearnerTestPanel таймер', () => {
  function fakeTimersResponse(expiresIso: string) {
    return (url: string) => {
      if (url === '/learning/me/tests/t1/my-attempts') {
        return Promise.resolve({ test_item_id: 't1', max_attempts: 3, submitted_count: 0, remaining_attempts: 3, attempts: [] })
      }
      if (url === '/learning/me/tests/t1/attempts') {
        return Promise.resolve({ ...ATTEMPT_VIEW, expires_at: expiresIso, time_limit_minutes: 30 })
      }
      if (url.startsWith('/learning/me/attempts/a1/submit')) return Promise.resolve(ATTEMPT_RESULT)
      return Promise.resolve({})
    }
  }

  it('показывает остаток времени, пока попытка не истекла', async () => {
    vi.useFakeTimers({ now: Date.parse('2026-08-29T12:00:00Z') })
    try {
      mockApi.mockImplementation(
        fakeTimersResponse('2026-08-29T12:10:00Z'),
      )
      const { default: LearnerTestPanel } = await import('../../src/components/learning/LearnerTestPanel.vue')
      const w = mountWith(LearnerTestPanel, { props: { item: COURSE.items[1], slug: 'kurs-1' } })
      await flushPromises()
      // старт/resume попытки переводит панель в фазу прохождения
      await w.findAll('button').find((b) => b.text().includes('learning.test.start'))!.trigger('click')
      await flushPromises()
      expect(w.find('.timer').exists()).toBe(true)
      expect(w.find('.timer--expired').exists()).toBe(false)
      expect(w.text()).toContain('learning.test.timeLeft')
    } finally {
      vi.useRealTimers()
    }
  })

  it('по истечении времени submit заблокирован и показан экспири-текст', async () => {
    mockApi.mockImplementation(
      fakeTimersResponse(new Date(Date.now() - 60_000).toISOString()),
    )
    const { default: LearnerTestPanel } = await import('../../src/components/learning/LearnerTestPanel.vue')
    const w = mountWith(LearnerTestPanel, { props: { item: COURSE.items[1], slug: 'kurs-1' } })
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('learning.test.start'))!.trigger('click')
    await flushPromises()
    expect(w.find('.timer--expired').exists()).toBe(true)
    const submit = w.findAll('button').find((b) => b.text().includes('learning.test.submit'))!
    expect(submit.attributes('disabled')).toBeDefined()
  })
})

describe('LearnerTestPanel', () => {
  async function mountPanel() {
    const { default: LearnerTestPanel } = await import('../../src/components/learning/LearnerTestPanel.vue')
    const w = mountWith(LearnerTestPanel, {
      props: { item: COURSE.items[1], slug: 'kurs-1' },
    })
    await flushPromises()
    return w
  }

  it('старт попытки: вопросы рендерятся, ответы отправляются, результат показан', async () => {
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/tests/t1/my-attempts') {
        return Promise.resolve({ test_item_id: 't1', max_attempts: 3, submitted_count: 0, remaining_attempts: 3, attempts: [] })
      }
      if (url === '/learning/me/tests/t1/attempts') return Promise.resolve(ATTEMPT_VIEW)
      if (url === '/learning/me/attempts/a1/submit') return Promise.resolve(ATTEMPT_RESULT)
      return Promise.resolve({})
    })

    const w = await mountPanel()
    const startBtn = w.findAll('button').find((b) => b.text().includes('learning.test.start'))!
    await startBtn.trigger('click')
    await flushPromises()

    expect(mockApi).toHaveBeenCalledWith('/learning/me/tests/t1/attempts', { method: 'POST' })
    expect(w.text()).toContain('Вопрос 1')

    await w.find('.n-checkbox-group').trigger('click')
    const submitBtn = w.findAll('button').find((b) => b.text().includes('learning.test.submit'))!
    await submitBtn.trigger('click')
    await flushPromises()

    expect(mockApi).toHaveBeenCalledWith('/learning/me/attempts/a1/submit', {
      method: 'POST',
      body: { answers: { q1: ['opt1'] } },
    })
    expect(w.find('.test-score__value').text()).toBe('100%')
  })

  it('вопросы листаются по одному; submit только на последнем и пока отвечены не все (ревью 2026-08-31)', async () => {
    const twoQuestions = {
      ...ATTEMPT_VIEW,
      questions: [
        { id: 'q1', text: 'Вопрос 1', multi: true, options: [{ id: 'opt1', text: 'Вариант' }] },
        { id: 'q2', text: 'Вопрос 2', multi: false, options: [{ id: 'opt2', text: 'Вариант' }] },
      ],
    }
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/tests/t1/my-attempts') {
        return Promise.resolve({ test_item_id: 't1', max_attempts: 3, submitted_count: 0, remaining_attempts: 3, attempts: [] })
      }
      if (url === '/learning/me/tests/t1/attempts') return Promise.resolve(twoQuestions)
      return Promise.resolve({})
    })

    const w = await mountPanel()
    await w.findAll('button').find((b) => b.text().includes('learning.test.start'))!.trigger('click')
    await flushPromises()

    // история вызовов предыдущих тестов не участвует в проверках этого
    mockApi.mockClear()

    const submitBtn = () => w.findAll('button').find((b) => b.text().includes('learning.test.submit'))
    const nextBtn = () => w.findAll('button').find((b) => b.text() === 'learning.test.next')
    const dots = () => w.findAll('.navigator__dot')

    // по одному вопросу: рендерится только первый
    expect(w.find('.question__text').text()).toBe('Вопрос 1')
    expect(w.find('.question .n-radio-group').exists()).toBe(false)
    // submit не на этом слайде — кнопки нет
    expect(submitBtn()).toBeUndefined()
    // навигатор: две точки, первая «отвечена» только после ответа
    expect(dots()).toHaveLength(2)
    expect(dots()[0].classes()).not.toContain('navigator__dot--answered')

    await w.find('.n-checkbox-group').trigger('click')
    await flushPromises()
    expect(dots()[0].classes()).toContain('navigator__dot--answered')
    expect(dots()[1].classes()).not.toContain('navigator__dot--answered')
    expect(w.text()).toContain('learning.test.answerAll')

    // «Далее» → вопрос 2
    await nextBtn()!.trigger('click')
    await flushPromises()
    expect(w.find('.question__text').text()).toBe('Вопрос 2')
    expect(w.find('.question .n-checkbox-group').exists()).toBe(false)

    // последний слайд: submit появился, но заблокирован — второй не отвечен
    expect(submitBtn()).toBeDefined()
    expect(submitBtn()!.attributes('disabled')).toBeDefined()

    // второй ответ → разблокировка, все ответы уходят
    await w.find('.n-radio-group').trigger('click')
    await flushPromises()
    expect(submitBtn()!.attributes('disabled')).toBeUndefined()
    await submitBtn()!.trigger('click')
    await flushPromises()
    expect(mockApi).toHaveBeenCalledWith('/learning/me/attempts/a1/submit', {
      method: 'POST',
      body: { answers: { q1: ['opt1'], q2: ['opt2'] } },
    })
  })

  it('навигатор возвращает к вопросу, ответ сохраняется; «Назад» на первом заблокирован', async () => {
    const twoQuestions = {
      ...ATTEMPT_VIEW,
      questions: [
        { id: 'q1', text: 'Вопрос 1', multi: true, options: [{ id: 'opt1', text: 'Вариант' }] },
        { id: 'q2', text: 'Вопрос 2', multi: false, options: [{ id: 'opt2', text: 'Вариант' }] },
      ],
    }
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/tests/t1/my-attempts') {
        return Promise.resolve({ test_item_id: 't1', max_attempts: 3, submitted_count: 0, remaining_attempts: 3, attempts: [] })
      }
      if (url === '/learning/me/tests/t1/attempts') return Promise.resolve(twoQuestions)
      return Promise.resolve({})
    })

    const w = await mountPanel()
    await w.findAll('button').find((b) => b.text().includes('learning.test.start'))!.trigger('click')
    await flushPromises()

    const prevBtn = () => w.findAll('button').find((b) => b.text() === 'learning.test.prev')!
    expect(prevBtn().attributes('disabled')).toBeDefined()

    await w.find('.n-checkbox-group').trigger('click')
    await w.findAll('button').find((b) => b.text() === 'learning.test.next')!.trigger('click')
    await flushPromises()
    expect(w.find('.question__text').text()).toBe('Вопрос 2')

    // прыжок точкой назад — ответ первого вопроса сохранён
    await w.findAll('.navigator__dot')[0].trigger('click')
    await flushPromises()
    expect(w.find('.question__text').text()).toBe('Вопрос 1')
    expect(w.find('.question .n-checkbox-group').exists()).toBe(true)
    expect(w.findAll('.navigator__dot')[0].classes()).toContain('navigator__dot--answered')
  })

  it('открытая попытка возобновляется через fetchAttempt', async () => {
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/tests/t1/my-attempts') {
        return Promise.resolve({
          test_item_id: 't1',
          max_attempts: 3,
          submitted_count: 0,
          remaining_attempts: 3,
          attempts: [{ id: 'a9', status: 'open', started_at: '2026-08-28T00:00:00Z' }],
        })
      }
      if (url === '/learning/me/attempts/a9') return Promise.resolve({ ...ATTEMPT_VIEW, id: 'a9' })
      return Promise.resolve({})
    })

    const w = await mountPanel()
    const resumeBtn = w.findAll('button').find((b) => b.text().includes('learning.test.resume'))!
    await resumeBtn.trigger('click')
    await flushPromises()

    expect(mockApi).toHaveBeenCalledWith('/learning/me/attempts/a9')
    expect(w.text()).toContain('Вопрос 1')
  })

  it('во время загрузки истории не предлагает старт и не объявляет безлимитные попытки', async () => {
    let finishHistory!: (history: unknown) => void
    mockApi.mockImplementation(() => new Promise((resolve) => { finishHistory = resolve }))
    const w = await mountPanel()
    expect(w.find('[role="status"]').text()).toBe('common.loading')
    expect(w.text()).not.toContain('learning.test.attemptsLeft')
    expect(w.text()).not.toContain('learning.test.start')
    finishHistory({ test_item_id: 't1', max_attempts: 3, submitted_count: 0, remaining_attempts: 3, attempts: [] })
    await flushPromises()
    expect(w.text()).toContain('learning.test.start')
  })

  it('ошибка истории закрывает старт; повтор успешно загружает историю', async () => {
    mockApi.mockRejectedValue(new Error('unavailable'))
    const w = await mountPanel()
    expect(w.find('.test-history-error').text()).toContain('learning.test.historyError')
    expect(w.text()).not.toContain('learning.test.start')
    expect(w.text()).not.toContain('learning.test.attemptsLeft')
    mockApi.mockResolvedValue({ test_item_id: 't1', max_attempts: 3, submitted_count: 0, remaining_attempts: 3, attempts: [] })
    await w.findAll('button').find((b) => b.text() === 'learning.page.retry')!.trigger('click')
    await flushPromises()
    expect(w.find('.test-history-error').exists()).toBe(false)
    expect(w.text()).toContain('learning.test.start')
  })

  it('после результата повторная попытка начинается только явным действием', async () => {
    mockApi.mockClear()
    mockApi.mockImplementation((url: string) => Promise.resolve(
      url === '/learning/me/tests/t1/my-attempts'
        ? { test_item_id: 't1', max_attempts: 3, submitted_count: 1, remaining_attempts: 2, attempts: [ATTEMPT_RESULT] }
        : ATTEMPT_VIEW,
    ))
    const w = await mountPanel()
    expect(w.find('.test-score__value').text()).toBe('100%')
    expect(w.findAll('button').some((b) => b.text() === 'learning.test.start')).toBe(false)
    expect(mockApi).not.toHaveBeenCalledWith('/learning/me/tests/t1/attempts', expect.anything())
    await w.findAll('button').find((b) => b.text() === 'learning.test.repeat')!.trigger('click')
    await flushPromises()
    expect(mockApi).toHaveBeenCalledWith('/learning/me/tests/t1/attempts', { method: 'POST' })
    expect(w.find('.question').exists()).toBe(true)
  })

  it('открытая попытка приоритетнее предыдущего результата и нулевого остатка', async () => {
    mockApi.mockImplementation((url: string) => Promise.resolve(
      url === '/learning/me/tests/t1/my-attempts'
        ? { test_item_id: 't1', max_attempts: 1, submitted_count: 1, remaining_attempts: 0,
          attempts: [{ id: 'a9', status: 'open', started_at: '2026-08-28T00:00:00Z' }, ATTEMPT_RESULT] }
        : { ...ATTEMPT_VIEW, id: 'a9' },
    ))
    const w = await mountPanel()
    expect(w.text()).not.toContain('learning.test.repeat')
    await w.findAll('button').find((b) => b.text() === 'learning.test.resume')!.trigger('click')
    await flushPromises()
    expect(mockApi).toHaveBeenCalledWith('/learning/me/attempts/a9')
    expect(w.find('.question').exists()).toBe(true)
  })

  it('отмена закрытия сохраняет ответы и активную попытку; подтверждение закрывает', async () => {
    mockDialogWarning.mockClear()
    mockApi.mockImplementation((url: string) => Promise.resolve(
      url === '/learning/me/tests/t1/my-attempts'
        ? { test_item_id: 't1', max_attempts: 3, submitted_count: 0, remaining_attempts: 3, attempts: [] }
        : url.endsWith('/submit') ? ATTEMPT_RESULT : ATTEMPT_VIEW,
    ))
    const w = await mountPanel()
    await w.findAll('button').find((b) => b.text() === 'learning.test.start')!.trigger('click')
    await flushPromises()
    await w.find('.n-checkbox-group').trigger('click')
    await w.findAll('button').find((b) => b.text() === 'common.close')!.trigger('click')
    expect(mockDialogWarning).toHaveBeenCalledWith(expect.objectContaining({
      content: 'learning.test.closeWarning', negativeText: 'learning.test.stayInTest',
    }))
    // Dismissing the confirmation invokes no positive callback: state stays put.
    expect(w.find('.question').exists()).toBe(true)
    const submit = w.findAll('button').find((b) => b.text() === 'learning.test.submit')!
    expect(submit.attributes('disabled')).toBeUndefined()
    await submit.trigger('click')
    await flushPromises()
    expect(mockApi).toHaveBeenCalledWith('/learning/me/attempts/a1/submit', {
      method: 'POST', body: { answers: { q1: ['opt1'] } },
    })
    // A new active attempt is also guarded, and explicit confirmation closes it.
    await w.findAll('button').find((b) => b.text() === 'learning.test.repeat')!.trigger('click')
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === 'common.close')!.trigger('click')
    mockDialogWarning.mock.lastCall![0].onPositiveClick()
    await flushPromises()
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('лимит исчерпан — нет бессмысленной кнопки старта', async () => {
    mockApi.mockResolvedValue({
      test_item_id: 't1', max_attempts: 1, submitted_count: 1, remaining_attempts: 0, attempts: [],
    })
    const w = await mountPanel()
    const startBtn = w.findAll('button').find((b) => b.text().includes('learning.test.start'))!
    expect(startBtn).toBeUndefined()
    expect(w.text()).toContain('learning.test.noAttemptsLeft')
  })
})

describe('LearnerCoursePage — error-state (ревью 2026-08-30)', () => {
  it('ошибка загрузки курса → alert с retry, а не вечная «Загрузка…»', async () => {
    mockApi.mockImplementation((url: string) => {
      if (url === '/learning/me/courses/kurs-1') return Promise.reject(new Error('boom'))
      return Promise.resolve({})
    })
    const { default: LearnerCoursePage } = await import('../../src/pages/learning/LearnerCoursePage.vue')
    const w = mountWith(LearnerCoursePage)
    await flushPromises()
    expect(w.find('.n-alert').exists()).toBe(true)
    const retry = w.findAll('button').find((b) => b.text().includes('learning.page.retry'))!
    expect(retry).toBeDefined()
  })
})
