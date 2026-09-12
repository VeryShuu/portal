/**
 * AdminPage: монтирование покрывает строки defineAsyncComponent новых вкладок
 * (matrix / messenger-outbox). У ``<script setup>`` константы GROUPS живут
 * внутри setup() — строки выполняются при любом mount страницы.
 *
 * Mount в shallow-режиме: дочерние компоненты (вкл. ленивые вкладки) не
 * рендерятся и их лоадеры не запускаются. Мокать .vue-модули вкладок нельзя:
 * VTU проверяет служебные экспорты (``__isTeleport``) у типов компонентов, а
 * module-mock Proxy бросает на обращении к несуществующему экспорту — на
 * медленном CI это выливается в unhandled rejection после конца теста.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const routeQuery: { tab: string | null } = { tab: null }

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { tab: routeQuery.tab } }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('naive-ui', () => ({
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'displayDirective'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  useMessage: () => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn() }),
}))

vi.mock('../../src/stores/modules', () => ({
  useModulesStore: () => ({ isEnabled: () => true }),
}))

import AdminPage from '../../src/pages/AdminPage.vue'

describe('AdminPage: вкладки группы «Уведомления»', () => {
  it('монтируется с tab=matrix (setup регистрирует новые вкладки)', () => {
    routeQuery.tab = 'matrix'
    const w = mount(AdminPage, { shallow: true })
    // Заголовок страницы отрендерен (собственный шаблон AdminPage); setup()
    // выполнился, включая defineAsyncComponent(MatrixTab/MessengerOutboxTab).
    expect(w.find('h1').text()).toBe('admin.title')
    routeQuery.tab = null
  })
})
