import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import { ref } from 'vue'

/**
 * Характеризующий тест виджета «Дни рождения на неделе».
 *
 * Контракты:
 * - рендерит список (ФИО + день месяца) когда есть именинники
 * - скрывается целиком (v-if на корне) когда список пуст
 * - день месяца извлекается из ISO birth_date (без месяца/года)
 */
const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru: { home: { birthdays: { title: 'Дни рождения на неделе' } } } },
})

vi.mock('naive-ui', () => ({
  NAvatar: {
    template: '<span class="n-avatar"><slot /></span>',
    props: ['round', 'size', 'src'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  ChevronBackOutline: { template: '<span />' },
  ChevronForwardOutline: { template: '<span />' },
}))

const mockRouterPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockRouterPush }),
}))

// Мокаем query: возвращаем управляемый ref с данными.
let mockData = ref<{ items: any[]; total: number } | undefined>(undefined)
vi.mock('../../src/queries/users', () => ({
  useBirthdaysQuery: () => ({ data: mockData }),
}))

describe('BirthdaysWidget', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockData = ref(undefined)
  })

  it('рендерит фамилию+имя (без отчества) и дату (день + месяц)', async () => {
    mockData = ref({
      items: [
        { id: 'u1', full_name: 'Иванов Иван Петрович', birth_date: '1990-03-12', avatar_url: null },
        { id: 'u2', full_name: 'Петрова Анна Сергеевна', birth_date: '1985-03-15', avatar_url: 'http://x/a.png' },
      ],
      total: 2,
    })

    const BirthdaysWidget = (await import('../../src/components/widgets/BirthdaysWidget.vue')).default
    const wrapper = mount(BirthdaysWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    const names = wrapper.findAll('.birthday-card__name').map((el) => el.text())
    const dates = wrapper.findAll('.birthday-card__date').map((el) => el.text())

    // Отчество отсекается — только фамилия + имя
    expect(names).toEqual(['Иванов Иван', 'Петрова Анна'])
    // ru-локаль: «день + месяц» (1990-03-12 → «12 марта», 1985-03-15 → «15 марта»)
    expect(dates).toEqual(['12 марта', '15 марта'])
  })

  it('клик по карточке открывает профиль /users/:id', async () => {
    mockData = ref({
      items: [{ id: 'user-42', full_name: 'Сидоров Пётр', birth_date: '1990-03-12', avatar_url: null }],
      total: 1,
    })

    const BirthdaysWidget = (await import('../../src/components/widgets/BirthdaysWidget.vue')).default
    const wrapper = mount(BirthdaysWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    await wrapper.find('.birthday-card').trigger('click')
    await flushPromises()
    expect(mockRouterPush).toHaveBeenCalledWith('/users/user-42')
  })

  it('скрыт (нет .widget), когда список именинников пуст', async () => {
    mockData = ref({ items: [], total: 0 })

    const BirthdaysWidget = (await import('../../src/components/widgets/BirthdaysWidget.vue')).default
    const wrapper = mount(BirthdaysWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.find('.widget').exists()).toBe(false)
    expect(wrapper.findAll('.birthday-row')).toHaveLength(0)
  })

  it('скрыт, пока данные не загружены (undefined)', async () => {
    mockData = ref(undefined)

    const BirthdaysWidget = (await import('../../src/components/widgets/BirthdaysWidget.vue')).default
    const wrapper = mount(BirthdaysWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.find('.widget').exists()).toBe(false)
  })
})
