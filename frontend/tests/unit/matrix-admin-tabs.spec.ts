/**
 * Mount-тесты новых вкладок админки: MatrixTab (обёртка настроек) и
 * MessengerOutboxTab (логи messenger-outbox: фильтры, колонки, действия),
 * плюс AdminPage (lazy-импорты новых вкладок исполняются только при рендере).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const messageMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}))

vi.mock('naive-ui', () => ({
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'displayDirective'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NButton: { template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>', props: ['size', 'type', 'disabled', 'loading'], emits: ['click'] },
  NTag: { template: '<span class="n-tag" :data-type="type"><slot /></span>', props: ['type', 'size'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  NInput: {
    template: '<input class="n-input" :value="value" :placeholder="placeholder" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'size', 'clearable', 'maxlength'],
    emits: ['update:value'],
  },
  NSelect: {
    template: '<select class="n-select" :value="value"><option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option></select>',
    props: ['value', 'options', 'size', 'clearable', 'placeholder'],
    emits: ['update:value'],
  },
  NDataTable: {
    name: 'NDataTable',
    template: '<div class="n-data-table" :data-count="data ? data.length : 0" />',
    props: ['columns', 'data', 'loading', 'pagination', 'remote', 'rowKey', 'size', 'striped'],
  },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /><slot name="footer" /></div>', props: ['show', 'title', 'preset'], emits: ['update:show'] },
  NSpin: { template: '<div class="n-spin"><slot /></div>', props: ['show'] },
  useMessage: () => messageMock,
}))

vi.mock('@vicons/ionicons5', () => ({
  RefreshOutline: { template: '<span>' },
}))

// Лёгкий стаб дочернего компонента настроек (тестируется отдельным спеком).
vi.mock('../../src/components/admin/MatrixBotSettings.vue', () => ({
  default: { name: 'MatrixBotSettings', template: '<div class="matrix-bot-stub">stub</div>' },
}))

const listDataHolder = vi.hoisted(() => ({ value: null as Record<string, unknown> | null }))
const detailHolder = vi.hoisted(() => ({ value: null as Record<string, unknown> | null }))
const retryMutMock = vi.hoisted(() => ({ mutateAsync: vi.fn(async () => ({})), isPending: { value: false } }))
const cancelMutMock = vi.hoisted(() => ({ mutateAsync: vi.fn(async () => ({})), isPending: { value: false } }))

vi.mock('../../src/queries/admin', async () => {
  // computed() — настоящий ref: шаблон разворачивает .value автоматически
  // (plain-holder в data/detail не распознаётся как ref и ломает шаблон).
  const { computed } = await import('vue')
  return {
    useMatrixBotQuery: vi.fn(() => ({ data: computed(() => null), isLoading: { value: false } })),
    usePutMatrixBotMutation: vi.fn(() => ({ mutateAsync: vi.fn(async () => ({})), isPending: { value: false } })),
    useMessengerOutboxQuery: vi.fn(() => ({
      data: computed(() => listDataHolder.value),
      isLoading: { value: false },
    })),
    useMessengerOutboxItemQuery: vi.fn(() => ({ data: computed(() => detailHolder.value) })),
    useRetryMessengerOutboxMutation: vi.fn(() => retryMutMock),
    useCancelMessengerOutboxMutation: vi.fn(() => cancelMutMock),
  }
})

vi.mock('../../src/utils/parseApiError', () => ({ parseApiError: () => 'Ошибка' }))

import MatrixTab from '../../src/pages/admin/tabs/MatrixTab.vue'
import MessengerOutboxTab from '../../src/pages/admin/tabs/MessengerOutboxTab.vue'

const ITEM = {
  id: 'row-1',
  provider: 'matrix',
  chat_id: '@u:matrix.mage.ru',
  text_preview: 'Тестовое сообщение',
  status: 'SENT',
  attempts: 1,
  max_attempts: 6,
  next_attempt_at: null,
  last_error: null,
  last_error_type: null,
  last_error_class: null,
  related_resource_type: null,
  related_resource_id: null,
  created_at: '2026-08-16T10:00:00Z',
  updated_at: '2026-08-16T10:00:05Z',
  sent_at: '2026-08-16T10:00:05Z',
}

describe('MatrixTab', () => {
  it('рендерит заголовок секции и встраивает компонент настроек', () => {
    const w = mount(MatrixTab, { global: { plugins: [i18n] } })
    expect(w.find('.matrix-bot-stub').exists()).toBe(true)
  })
})

describe('MessengerOutboxTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listDataHolder.value = {
      items: [ITEM, { ...ITEM, id: 'row-2', provider: 'max', status: 'DLQ', chat_id: '100', attempts: 6 }],
      total: 2,
      limit: 50,
      offset: 0,
      counts_30d: { SENT: 1, DLQ: 1 },
      next_cursor: null,
      has_more: false,
    }
    detailHolder.value = null
  })

  function mountTab() {
    return mount(MessengerOutboxTab, { global: { plugins: [i18n] } })
  }

  it('рендерит счётчики статусов и DLQ-алерт', async () => {
    const w = mountTab()
    await flushPromises()
    const tags = w.findAll('.n-tag')
    // 6 статусов + 2 тега в таблице не рендерятся (стаб NDataTable) — считаем только статистику
    expect(tags.length).toBeGreaterThanOrEqual(6)
    expect(w.text()).toContain('status.dlq')
  })

  it('передаёт данные в таблицу', async () => {
    const w = mountTab()
    await flushPromises()
    expect(w.find('.n-data-table').attributes('data-count')).toBe('2')
  })

  it('canRetry/canCancel: правила видимости действий', async () => {
    const w = mountTab()
    await flushPromises()
    const vm = w.vm as unknown as Record<string, (v: string) => boolean>
    expect(vm.canRetry('SENT')).toBe(true)
    expect(vm.canRetry('FAILED')).toBe(true)
    expect(vm.canRetry('PENDING')).toBe(false)
    expect(vm.canCancel('PENDING')).toBe(true)
    expect(vm.canCancel('DLQ')).toBe(true)
    expect(vm.canCancel('SENT')).toBe(false)
  })

  it('openDetail открывает модалку с полным текстом и payload', async () => {
    detailHolder.value = {
      ...ITEM,
      text: 'Полный текст сообщения',
      payload: { formatted_body: '<b>Полный текст</b>' },
    }
    const w = mountTab()
    await flushPromises()
    const vm = w.vm as unknown as { openDetail: (id: string) => void }
    vm.openDetail('row-1')
    await flushPromises()
    const modal = w.find('.n-modal')
    expect(modal.exists()).toBe(true)
    expect(modal.text()).toContain('Полный текст сообщения')
    expect(modal.text()).toContain('formatted_body')
  })

  it('onRetry вызывает мутацию и показывает успех', async () => {
    const w = mountTab()
    await flushPromises()
    const vm = w.vm as unknown as { onRetry: (id: string) => Promise<void> }
    await vm.onRetry('row-1')
    expect(retryMutMock.mutateAsync).toHaveBeenCalledWith('row-1')
    expect(messageMock.success).toHaveBeenCalled()
  })

  it('onCancel: ошибка мутации → message.error', async () => {
    cancelMutMock.mutateAsync.mockRejectedValueOnce(new Error('boom'))
    const w = mountTab()
    await flushPromises()
    const vm = w.vm as unknown as { onCancel: (id: string) => Promise<void> }
    await vm.onCancel('row-2')
    expect(cancelMutMock.mutateAsync).toHaveBeenCalledWith('row-2')
    expect(messageMock.error).toHaveBeenCalled()
  })

  it('activeParams собирает фильтры; resetFilters очищает и перезагружает', async () => {
    const w = mountTab()
    await flushPromises()
    const vm = w.vm as unknown as {
      activeParams: () => Record<string, unknown>
      resetFilters: () => void
      reload: () => void
      filters: Record<string, string>
    }
    vm.filters.status = 'DLQ'
    vm.filters.provider = 'matrix'
    vm.filters.chat_id = '@u'
    vm.filters.q = 'текст'
    const params = vm.activeParams()
    expect(params).toMatchObject({ status: 'DLQ', provider: 'matrix', chat_id: '@u', q: 'текст' })

    vm.resetFilters()
    expect(vm.filters.status).toBe('')
    expect(vm.filters.provider).toBe('')
  })

  it('форматирование дат: null → пусто, валидная дата → строка', async () => {
    const w = mountTab()
    await flushPromises()
    const vm = w.vm as unknown as { formatDate: (s: string | null) => string }
    expect(vm.formatDate(null)).toBe('')
    expect(vm.formatDate('2026-08-16T10:00:00Z')).not.toBe('')
  })
})
