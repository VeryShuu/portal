import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import { ref } from 'vue'

/**
 * Виджет «Мои встречи» — характеризующий тест.
 * Контракты (редизайн):
 * - рендерит список бронирований когда они есть
 * - компактный empty-state с заголовком + hint (без большого пустого пространства)
 * - скрыт целиком, когда модуль meetings выключен
 */
const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    ru: {
      meetings: {
        widget: {
          title: 'Мои встречи',
          viewAll: 'Смотреть все',
          noMeetings: 'Нет предстоящих встреч',
        },
      },
      home: { meetings: { noMeetingsHint: 'Хорошего продуктивного дня!' } },
    },
  },
})

vi.mock('naive-ui', () => ({
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size'] },
}))

const mockRouterPush = vi.fn()
vi.mock('vue-router', () => ({
  RouterLink: { template: '<a class="router-link"><slot /></a>', props: ['to'] },
  useRouter: () => ({ push: mockRouterPush }),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
}))

// Управляемый query: { data, isLoading } как refs.
let mockData = ref<any[] | undefined>(undefined)
let mockLoading = ref(false)
vi.mock('../../src/queries/meetings', () => ({
  useMyMeetingBookingsQuery: () => ({ data: mockData, isLoading: mockLoading }),
}))

// Модули: по умолчанию meetings включён (show=true).
let meetingsEnabled = true
vi.mock('../../src/stores/modules', () => ({
  useModulesStore: () => ({
    isEnabled: () => meetingsEnabled,
    load: vi.fn(),
  }),
}))

describe('MeetingsWidget', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mockData = ref(undefined)
    mockLoading = ref(false)
    meetingsEnabled = true
  })

  it('рендерит список встреч когда есть бронирования', async () => {
    mockData = ref([
      {
        id: 'b1',
        title: 'Планёрка',
        start_time: '2026-08-07T10:00:00',
        end_time: '2026-08-07T11:00:00',
        rooms: [{ name: 'Переговорка А' }],
      },
    ])

    const MeetingsWidget = (await import('../../src/components/widgets/MeetingsWidget.vue')).default
    const wrapper = mount(MeetingsWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.findAll('.meetings-widget__item')).toHaveLength(1)
    expect(wrapper.text()).toContain('Планёрка')
  })

  it('показывает компактный empty-state с заголовком и hint', async () => {
    mockData = ref([])

    const MeetingsWidget = (await import('../../src/components/widgets/MeetingsWidget.vue')).default
    const wrapper = mount(MeetingsWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.find('.meetings-widget__empty').exists()).toBe(true)
    expect(wrapper.find('.meetings-widget__empty-title').text()).toContain('Нет предстоящих встреч')
    expect(wrapper.find('.meetings-widget__empty-hint').text()).toContain('Хорошего продуктивного дня!')
    // Список не рендерится
    expect(wrapper.find('.meetings-widget__list').exists()).toBe(false)
  })

  it('скрыт целиком, когда модуль meetings выключен', async () => {
    meetingsEnabled = false
    mockData = ref([])

    const MeetingsWidget = (await import('../../src/components/widgets/MeetingsWidget.vue')).default
    const wrapper = mount(MeetingsWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.find('.widget').exists()).toBe(false)
  })
})
