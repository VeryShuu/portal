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

  it('рендерит ФИО и день месяца при наличии именинников', async () => {
    mockData = ref({
      items: [
        { full_name: 'Иванов Иван', birth_date: '1990-03-12', avatar_url: null },
        { full_name: 'Петрова Анна', birth_date: '1985-03-15', avatar_url: 'http://x/a.png' },
      ],
      total: 2,
    })

    const BirthdaysWidget = (await import('../../src/components/widgets/BirthdaysWidget.vue')).default
    const wrapper = mount(BirthdaysWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    const names = wrapper.findAll('.birthday-row__name').map((el) => el.text())
    const days = wrapper.findAll('.birthday-row__day').map((el) => el.text())

    expect(names).toEqual(['Иванов Иван', 'Петрова Анна'])
    // 1990-03-12 → 12, 1985-03-15 → 15 (только день, без месяца/года)
    expect(days).toEqual(['12', '15'])
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
