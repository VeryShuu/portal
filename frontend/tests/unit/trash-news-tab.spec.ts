/**
 * Unit-тесты TrashNewsTab.vue — вкладка «Новости» корзины.
 *
 * Покрытие:
 * - загрузка списка через listTrashNews (page/page_size по умолчанию)
 * - колонка deleted_at: без даты → '—', с датой → formatDate(...)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const listTrashNewsMock = vi.fn()

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'ru' } }),
}))

vi.mock('naive-ui', () => ({
  NDataTable: {
    name: 'NDataTable',
    template: '<div class="n-data-table" />',
    props: ['columns', 'data', 'loading', 'pagination', 'bordered', 'size'],
  },
  NPagination: {
    name: 'NPagination',
    template: '<div class="n-pagination" />',
    props: ['page', 'pageCount', 'pageSize', 'pageSizes', 'showSizePicker'],
    emits: ['update:page', 'update:page-size'],
  },
  NButton: {
    template: '<button><slot /></button>',
    props: ['size', 'type', 'quaternary'],
  },
  NPopconfirm: {
    template: '<div class="n-popconfirm"><slot name="trigger" /><slot /></div>',
    emits: ['positive-click'],
  },
  NSpace: { template: '<div class="n-space"><slot /></div>', props: ['size'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  RefreshOutline: { template: '<span />' },
  TrashBinOutline: { template: '<span />' },
}))

vi.mock('../../src/api/news', () => ({
  listTrashNews: (...args: unknown[]) => listTrashNewsMock(...args),
  restoreNews: vi.fn(),
  purgeNews: vi.fn(),
}))

vi.mock('../../src/components/EmptyState.vue', () => ({
  default: { name: 'EmptyState', template: '<div class="empty-state" />' },
}))

import TrashNewsTab from '../../src/components/trash/TrashNewsTab.vue'

function makeTrashItem(overrides: Record<string, unknown> = {}) {
  return {
    id: 'n-1',
    title: 'Удалённая новость',
    status: 'published',
    previous_status: 'published',
    deleted_at: '2026-08-01T10:00:00Z',
    author: null,
    ...overrides,
  } as never
}

describe('TrashNewsTab.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    listTrashNewsMock.mockReset()
    listTrashNewsMock.mockResolvedValue({ items: [makeTrashItem()], total: 1 })
  })

  it('загружает список при монтировании (page=1, page_size=20)', async () => {
    const wrapper = mount(TrashNewsTab)
    await flushPromises()

    expect(listTrashNewsMock).toHaveBeenCalledWith({ page: 1, page_size: 20 })
    const table = wrapper.findComponent({ name: 'NDataTable' })
    expect(table.exists()).toBe(true)
    expect((table.props('data') as unknown[])).toHaveLength(1)
  })

  it('колонка deleted_at: без даты → прочерк, с датой → форматированная дата', async () => {
    const wrapper = mount(TrashNewsTab)
    await flushPromises()

    const columns = wrapper
      .findComponent({ name: 'NDataTable' })
      .props('columns') as Array<Record<string, any>>
    const deletedAtCol = columns.find((c) => c.key === 'deleted_at')!

    // Без deleted_at (undefined/null) — прочерк, а не Invalid Date.
    expect(deletedAtCol.render(makeTrashItem({ deleted_at: undefined }))).toBe('—')
    expect(deletedAtCol.render(makeTrashItem({ deleted_at: null }))).toBe('—')

    // С датой — formatDate(iso, 'ru') → «1 авг. 2026 г.» (год обязан присутствовать).
    const formatted = deletedAtCol.render(makeTrashItem({ deleted_at: '2026-08-01T10:00:00Z' }))
    expect(formatted).not.toBe('—')
    expect(formatted).toContain('2026')
  })
})
