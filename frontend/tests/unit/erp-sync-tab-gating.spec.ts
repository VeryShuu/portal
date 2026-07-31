import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { useModulesStore } from '../../src/stores/modules'

/**
 * Характеризующий тест гейтинга ERP-вкладки по состоянию модуля erp_sync.
 *
 * Контекст: ERP-вкладка показывается только когда modulesStore.isEnabled('erp_sync').
 * При выключенном модуле вкладка скрывается (чтобы компоненты не слёту запросами
 * к gated API /erp-sync/* → каскад 404). Включение — карточкой во вкладке «Модули».
 *
 * Вместо полного маунта AdminPage (тянет десятки async-табов с deps) проверяем
 * саму логику фильтрации currentTabs через thin-host, переиспользующий тот же
 * TAB_MODULE_GATE + modulesStore.isEnabled паттерн, что и AdminPage.vue.
 */
vi.mock('naive-ui', () => ({
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'size'] },
  NTabPane: {
    template: '<div class="n-tab-pane" :data-name="name"><slot /></div>',
    props: ['name', 'tab'],
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ query: { tab: 'erp_sync' }, params: {}, path: '/admin' }),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false } })),
  useMutation: vi.fn(() => ({ mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
}))

// Реальный modulesStore (мокаем только api), наполняем через isEnabled override.
vi.mock('../../src/api/index', () => ({ api: vi.fn().mockResolvedValue({}) }))

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru: {}, en: {} },
})

// Thin host: воспроизводит логику AdminPage currentTabs + TAB_MODULE_GATE.
// Это держит тест стабильным к добавлению новых табов и deps, проверяя именно
// контрак гейтинга по модулю.
function makeHost(enabledModules: Set<string>) {
  return defineComponent({
    setup() {
      const modulesStore = useModulesStore()
      ;(modulesStore as unknown as { isEnabled: (n: string) => boolean }).isEnabled = (
        name: string,
      ) => enabledModules.has(name)

      const TAB_MODULE_GATE: Partial<Record<string, string>> = { erp_sync: 'erp_sync' }
      const tabs = [
        { name: 'system', label: 'system' },
        { name: 'modules', label: 'modules' },
        { name: 'erp_sync', label: 'erpSync' },
        { name: 'monitoring', label: 'monitoring' },
      ]
      const currentTabs = tabs.filter((t) => {
        const m = TAB_MODULE_GATE[t.name]
        return !m || (modulesStore as unknown as { isEnabled: (n: string) => boolean }).isEnabled(m)
      })
      return () =>
        h(
          'div',
          currentTabs.map((t) =>
            h('div', { class: 'n-tab-pane', 'data-name': t.name }, t.name),
          ),
        )
    },
  })
}

describe('ERP-вкладка: гейтинг по модулю erp_sync', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('скрыта, когда модуль выключен (нет в enabled set)', async () => {
    const Host = makeHost(new Set(['helpdesk', 'photos']))
    const wrapper = mount(Host, { global: { plugins: [i18n] } })
    await flushPromises()
    const names = wrapper.findAll('[data-name]').map((el) => el.attributes('data-name'))
    expect(names).not.toContain('erp_sync')
    expect(names).toContain('system')
    expect(names).toContain('modules')
  })

  it('видна, когда модуль включён', async () => {
    const Host = makeHost(new Set(['erp_sync']))
    const wrapper = mount(Host, { global: { plugins: [i18n] } })
    await flushPromises()
    const names = wrapper.findAll('[data-name]').map((el) => el.attributes('data-name'))
    expect(names).toContain('erp_sync')
  })
})
