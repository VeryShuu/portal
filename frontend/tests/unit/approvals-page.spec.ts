/**
 * ApprovalsPage.vue: рендер списка, empty-state, чекбоксы и массовое
 * согласование, quick-approve, открытие карточки. ApprovalDetailDrawer
 * заглушается — он покрыт отдельным спеком.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, computed } from 'vue'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template:
      '<button class="n-button" :disabled="disabled" :data-loading="loading ? \'1\' : undefined" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'loading', 'disabled'],
    emits: ['click'],
  },
  NCard: { template: '<div class="n-card"><slot /></div>', props: ['size', 'hoverable'] },
  NCheckbox: {
    template:
      '<input type="checkbox" class="n-checkbox" :checked="checked" @change="$emit(\'update:checked\', $event.target.checked)" />',
    props: ['checked'],
    emits: ['update:checked'],
  },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'showIcon'] },
  NInput: {
    template: '<input class="n-input" :value="value" :placeholder="placeholder" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'clearable', 'size'],
    emits: ['update:value'],
  },
  NIcon: { template: '<i><slot /></i>' },
  NSpin: { template: '<div class="n-spin"><slot /></div>' },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['size', 'type'] },
  NTooltip: { template: '<div class="n-tooltip"><slot name="trigger" /><slot /></div>' },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  LockClosedOutline: { template: '<i class="lock" />' },
  StorefrontOutline: { template: '<i class="storefront" />' },
  ArchiveOutline: { template: '<i class="archive" />' },
  InformationCircleOutline: { template: '<i class="info" />' },
  RefreshOutline: { template: '<i class="refresh" />' },
}))

vi.mock('../../src/components/EmptyState.vue', () => ({
  default: { template: '<div class="empty-state">{{ title }}</div>', props: ['title', 'description'] },
}))

vi.mock('../../src/components/approvals/BulkApproveReport.vue', () => ({
  default: {
    template:
      '<div class="bulk-report-stub" :data-approved="String(approved)"><button class="report-close" @click="$emit(\'dismiss\')" /></div>',
    props: ['approved', 'failed', 'rows'],
    emits: ['dismiss'],
  },
}))

vi.mock('../../src/components/approvals/ApprovalDetailDrawer.vue', () => ({
  default: {
    template: '<div class="drawer-stub" :data-show="String(show)" />',
    props: ['show', 'loading', 'error', 'running', 'doc', 'comment', 'managerGuid'],
    emits: ['close', 'retry', 'approve', 'reject', 'update:comment', 'update:managerGuid'],
  },
}))

const selectedSet = ref<Set<string>>(new Set())

const pageState = {
  items: ref<Record<string, unknown>[]>([]),
  filteredItems: ref<Record<string, unknown>[]>([]),
  loading: ref(false),
  listError: ref(false),
  refreshing: ref(false),
  search: ref(''),
  selected: selectedSet,
  selectedCount: computed(() => selectedSet.value.size),
  allSelected: ref(false),
  bulkEligible: ref<Record<string, unknown>[]>([]),
  actionRunning: ref(false),
  drawerOpen: ref(false),
  drawerUuid: ref<string | null>(null),
  detail: ref(null),
  detailLoading: ref(false),
  detailError: ref(false),
  comment: ref(''),
  managerGuid: ref<string | null>(null),
  bulkReport: ref<{ approved: number; failed: number; rows: unknown[] } | null>(null),
  toggleSelected: vi.fn(),
  toggleSelectAll: vi.fn(),
  reload: vi.fn().mockResolvedValue(undefined),
  refresh: vi.fn().mockResolvedValue(undefined),
  retryDetail: vi.fn(),
  dismissBulkReport: vi.fn(),
  bulkApproveSelected: vi.fn().mockResolvedValue(undefined),
  quickApprove: vi.fn().mockResolvedValue(undefined),
  openDrawer: vi.fn(),
  closeDrawer: vi.fn(),
  approveCurrent: vi.fn().mockResolvedValue(undefined),
  rejectCurrent: vi.fn().mockResolvedValue(undefined),
}

vi.mock('../../src/pages/composables/useApprovalsPage', () => ({
  useApprovalsPage: () => pageState,
}))

import ApprovalsPage from '../../src/pages/approvals/ApprovalsPage.vue'

function doc(guid: string, requiresManager = false) {
  return {
    guid,
    doc_type: 'ЗаказПоставщику',
    number: `УП-${guid}`,
    date: '04.09.2026',
    organization: 'МАГЭ',
    manager: 'Иванов',
    comment: '',
    contractor: 'ООО П',
    project: null,
    amount: 100,
    currency: 'RUB',
    activity_direction: null,
    requires_manager: requiresManager,
    has_prices: true,
    history: [],
    products: [],
    managers: [],
  }
}

async function mountPage() {
  const w = mount(ApprovalsPage, { global: { plugins: [i18n] } })
  await flushPromises()
  return w
}

describe('ApprovalsPage.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    selectedSet.value = new Set()
    pageState.drawerOpen.value = false
    pageState.loading.value = false
    pageState.listError.value = false
    pageState.detailError.value = false
    pageState.refreshing.value = false
    pageState.search.value = ''
    pageState.bulkReport.value = null
    pageState.items.value = []
    pageState.filteredItems.value = []
  })

  it('loading — спиннер', async () => {
    pageState.loading.value = true
    const w = await mountPage()
    expect(w.find('.apr__loader').exists()).toBe(true)
  })

  it('ошибка списка — алерт с повтором вместо пустой очереди', async () => {
    // Ревью 2026-09-05: ошибка загрузки выглядела как «нет документов».
    pageState.listError.value = true
    const w = await mountPage()
    expect(w.find('.n-alert').exists()).toBe(true)
    expect(w.find('.empty-state').exists()).toBe(false)
    const retry = w.findAll('.n-button').find((b) => b.text().includes('approvals.retry'))
    expect(retry).toBeDefined()
    await retry!.trigger('click')
    expect(pageState.refresh).toHaveBeenCalled()
  })

  it('пустой список — EmptyState', async () => {
    const w = await mountPage()
    expect(w.find('.empty-state').exists()).toBe(true)
  })

  it('пустой поиск — EmptyState с поисковым заголовком', async () => {
    pageState.search.value = 'УП-404'
    const w = await mountPage()
    expect(w.find('.empty-state').exists()).toBe(true)
    expect(w.find('.empty-state').text()).toContain('searchEmpty')
  })

  it('отчёт партии рендерится, dismiss прокидывается', async () => {
    pageState.filteredItems.value = [doc('a')]
    pageState.bulkReport.value = { approved: 1, failed: 0, rows: [{ uuid: 'a' }] }
    const w = await mountPage()
    const report = w.find('.bulk-report-stub')
    expect(report.exists()).toBe(true)
    expect(report.attributes('data-approved')).toBe('1')
    await w.find('.report-close').trigger('click')
    expect(pageState.dismissBulkReport).toHaveBeenCalled()
  })

  it('кнопка «Обновить» вызывает refresh', async () => {
    pageState.filteredItems.value = [doc('a')]
    const w = await mountPage()
    const refresh = w.find('.apr__filters .n-button')
    expect(refresh.exists()).toBe(true)
    await refresh.trigger('click')
    expect(pageState.refresh).toHaveBeenCalled()
  })

  it('рендерит карточки документов и bulk-кнопку', async () => {
    pageState.filteredItems.value = [doc('a'), doc('b')]
    pageState.bulkEligible.value = [doc('a'), doc('b')]
    const w = await mountPage()
    expect(w.findAll('.apr__card').length).toBe(2)
    expect(w.text()).toContain('УП-a')
  })

  it('кнопка bulk вызывает bulkApproveSelected', async () => {
    pageState.filteredItems.value = [doc('a')]
    pageState.selected.value = new Set(['a'])
    const w = await mountPage()
    const bulk = w.find('.apr__toolbar .n-button')
    expect((bulk.element as HTMLButtonElement).disabled).toBe(false)
    await bulk.trigger('click')
    expect(pageState.bulkApproveSelected).toHaveBeenCalled()
  })

  it('quick-approve не доступен для requires_manager, доступен для обычного', async () => {
    pageState.filteredItems.value = [doc('a'), doc('locked', true)]
    const w = await mountPage()
    // Кнопка «Согласовать» (i18n-ключ) есть только у карточки без requires_manager
    const approveButtons = w
      .findAll('.apr__card-actions .n-button')
      .filter((b) => b.text().includes('actions.approve'))
    expect(approveButtons.length).toBe(1)
    await approveButtons[0].trigger('click')
    expect(pageState.quickApprove).toHaveBeenCalled()
  })

  it('«Подробнее» открывает drawer', async () => {
    pageState.filteredItems.value = [doc('a')]
    const w = await mountPage()
    const details = w
      .findAll('.apr__card-actions .n-button')
      .find((b) => b.text().includes('approvals.details'))
    await details?.trigger('click')
    expect(pageState.openDrawer).toHaveBeenCalledWith('a')
  })

  it('карточка без суммы — прочерк в проекте, суммы нет', async () => {
    pageState.filteredItems.value = [{ ...doc('a'), amount: null, project: null }]
    const w = await mountPage()
    expect(w.text()).toContain('—')
  })

  it('длинный проект обрезается до 60 символов с многоточием', async () => {
    const longProject = 'ИГИ, строительство ПВОЛС, № 25281879789425541640066664/МАГЭ от 23.06.2026'
    pageState.filteredItems.value = [{ ...doc('a'), project: longProject }]
    const w = await mountPage()
    expect(w.text()).toContain(longProject.slice(0, 60) + '…')
    expect(w.text()).not.toContain(longProject)
  })

  it('тип заказа — иконка с названием в title (поставщик → магазин, внутренний → склад)', async () => {
    pageState.filteredItems.value = [doc('a'), { ...doc('b'), has_prices: false }]
    const w = await mountPage()
    const types = w.findAll('.apr__card-type')
    expect(types.length).toBe(2)
    // i18n-заглушка рендерит ключ как есть
    expect(types[0].attributes('title')).toContain('types.supplier')
    expect(types[1].attributes('title')).toContain('types.internal')
    expect(types[0].find('.storefront').exists()).toBe(true)
    expect(types[1].find('.archive').exists()).toBe(true)
  })

  it('внутренний заказ (v2.1.0.0): без чекбокса и quick-approve; замок при requires_manager', async () => {
    pageState.filteredItems.value = [
      doc('a'),
      {
        ...doc('internal'),
        has_prices: false,
        doc_type: 'ЗаказНаВнутреннееПотребление',
        requires_manager: true,
      },
    ]
    const w = await mountPage()
    const internalCard = w.findAll('.apr__card')[1]
    // Быстрое «Согласовать» — только у карточки поставщика
    expect(internalCard.find('.apr__card-actions .n-button').text()).toContain('details')
    expect(
      internalCard.findAll('.apr__card-actions .n-button').filter((b) => b.text().includes('approve')).length,
    ).toBe(0)
    // Чекбокса нет (из bulk исключён), при requires_manager — замок
    expect(internalCard.find('input[type=checkbox]').exists()).toBe(false)
    expect(internalCard.find('.apr__card-lock').exists()).toBe(true)
    // Заглушки «временно недоступно» больше нет — внутренние согласуются
    expect(internalCard.find('.apr__card-unavailable').exists()).toBe(false)
    // У карточки поставщика всё на месте
    const supplierCard = w.findAll('.apr__card')[0]
    expect(supplierCard.find('input[type=checkbox]').exists()).toBe(true)
    expect(supplierCard.find('.apr__card-unavailable').exists()).toBe(false)
  })

  it('внутренний заказ без ответственного — без замка (согласуется как есть)', async () => {
    pageState.filteredItems.value = [
      {
        ...doc('internal'),
        has_prices: false,
        doc_type: 'ЗаказНаВнутреннееПотребление',
        requires_manager: false,
      },
    ]
    const w = await mountPage()
    const card = w.findAll('.apr__card')[0]
    expect(card.find('.apr__card-lock').exists()).toBe(false)
    expect(card.find('input[type=checkbox]').exists()).toBe(false)
  })
})
