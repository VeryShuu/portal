import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import { ref } from 'vue'

/**
 * Характеризующий тест виджета «Ближайшие дни рождения сотрудников».
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
  messages: { ru: { home: { birthdays: { title: 'Ближайшие дни рождения сотрудников' } } } },
})

vi.mock('naive-ui', () => ({
  NAvatar: {
    template: '<span class="n-avatar"><slot /></span>',
    props: ['round', 'size', 'src'],
  },
  NButton: { template: '<button class="n-button"><slot /></button>' },
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

  it('рендерит фамилию+имя (без отчества) и дату (день + месяц) списком', async () => {
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

    const names = wrapper.findAll('.birthday-row__name').map((el) => el.text())
    const dates = wrapper.findAll('.birthday-row__date').map((el) => el.text())

    // Отчество отсекается — только фамилия + имя; рендерится списком (ТЗ п.8)
    expect(names).toEqual(['Иванов Иван', 'Петрова Анна'])
    // ru-локаль: «день + месяц» (1990-03-12 → «12 марта», 1985-03-15 → «15 марта»)
    expect(dates).toEqual(['12 марта', '15 марта'])
  })

  it('клик по строке открывает профиль /users/:id', async () => {
    mockData = ref({
      items: [{ id: 'user-42', full_name: 'Сидоров Пётр', birth_date: '1990-03-12', avatar_url: null }],
      total: 1,
    })

    const BirthdaysWidget = (await import('../../src/components/widgets/BirthdaysWidget.vue')).default
    const wrapper = mount(BirthdaysWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    await wrapper.find('.birthday-row__btn').trigger('click')
    await flushPromises()
    expect(mockRouterPush).toHaveBeenCalledWith('/users/user-42')
  })

  it('ограничивает список VISIBLE_LIMIT и не рендерит карусель/paging', async () => {
    // 8 именинников, VISIBLE_LIMIT=4 → рендерятся 4, paging/dots/arrows отсутствуют
    const items = Array.from({ length: 8 }, (_, i) => ({
      id: `u${i}`,
      full_name: `Фамилия${i} Имя${i}`,
      birth_date: '1990-03-12',
      avatar_url: null,
    }))
    mockData = ref({ items, total: 8 })

    const BirthdaysWidget = (await import('../../src/components/widgets/BirthdaysWidget.vue')).default
    const wrapper = mount(BirthdaysWidget, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.findAll('.birthday-row')).toHaveLength(4)
    // Карусель убрана (ТЗ п.8): нет стрелок и точек-индикаторов
    expect(wrapper.find('.nav-arrow').exists()).toBe(false)
    expect(wrapper.find('.dots').exists()).toBe(false)
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
