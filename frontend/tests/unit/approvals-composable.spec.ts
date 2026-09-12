/**
 * useApprovalsPage (src/pages/composables/useApprovalsPage.ts): выбор
 * чекбоксами, bulk-eligible, все действия через мутации, бизнес-правила
 * (requires_manager исключён из массового; отклонение требует комментарий).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const capturedMutations: { mutationFn?: (args: unknown) => Promise<unknown> }[] = []
const listRefetch = vi.fn().mockResolvedValue(undefined)
const detailRefetch = vi.fn().mockResolvedValue(undefined)
const messageSuccess = vi.fn()
const messageError = vi.fn()
const messageWarning = vi.fn()

const listData = ref<{ items: unknown[]; total: number }>({ items: [], total: 0 })
const listIsLoading = ref(false)
const listIsFetching = ref(false)
const listIsError = ref(false)
const detailIsLoading = ref(false)
const detailIsError = ref(false)

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('naive-ui', () => ({ useMessage: () => ({ success: messageSuccess, error: messageError, warning: messageWarning }) }))

const approveMutate = vi.fn().mockResolvedValue({ ok: true, message: 'Согласовано' })
const rejectMutate = vi.fn().mockResolvedValue({ ok: true, message: 'Отклонено' })
const bulkMutate = vi.fn().mockResolvedValue({ results: [], approved: 2, failed: 0 })

vi.mock('../../src/queries/approvals', () => ({
  useApprovalsQuery: () => ({
    data: listData,
    isLoading: listIsLoading,
    isFetching: listIsFetching,
    isError: listIsError,
    refetch: listRefetch,
  }),
  useApprovalDetailQuery: () => ({
    data: ref({
      guid: 'g-1',
      doc_type: 'ЗаказПоставщику',
      has_prices: true,
      number: 'УП-1',
      date: '04.09.2026',
      organization: 'МАГЭ',
      manager: 'Ив',
      comment: '',
      requires_manager: false,
      history: [],
      products: [],
      managers: [],
      attachments: [],
    }),
    isLoading: detailIsLoading,
    isError: detailIsError,
    refetch: detailRefetch,
  }),
  useApproveMutation: () => ({ mutateAsync: approveMutate, isPending: ref(false) }),
  useRejectMutation: () => ({ mutateAsync: rejectMutate, isPending: ref(false) }),
  useBulkApproveMutation: () => ({ mutateAsync: bulkMutate, isPending: ref(false) }),
}))

import { BULK_APPROVE_MAX } from '../../src/api/approvals'
import { useApprovalsPage } from '../../src/pages/composables/useApprovalsPage'

function doc(guid: string, requiresManager = false) {
  return {
    guid,
    doc_type: 'ЗаказПоставщику',
    number: guid,
    date: '04.09.2026',
    organization: 'МАГЭ',
    manager: '',
    comment: '',
    requires_manager: requiresManager,
    has_prices: true,
    history: [],
    products: [],
    managers: [],
  }
}

describe('useApprovalsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    capturedMutations.length = 0
    listIsLoading.value = false
    listIsFetching.value = false
    listIsError.value = false
    detailIsLoading.value = false
    detailIsError.value = false
    listData.value = { items: [doc('a'), doc('b'), doc('c', true)], total: 3 }
  })

  it('bulkEligible исключает requires_manager', () => {
    const page = useApprovalsPage()
    expect(page.bulkEligible.value.map((d) => d.guid)).toEqual(['a', 'b'])
  })

  it('bulkEligible исключает внутренние заказы (информационно)', () => {
    listData.value = {
      items: [
        { ...doc('a'), has_prices: false, doc_type: 'ЗаказНаВнутреннееПотребление' },
        doc('b'),
      ],
      total: 2,
    }
    const page = useApprovalsPage()
    expect(page.bulkEligible.value.map((d) => d.guid)).toEqual(['b'])
  })

  it('toggleSelectAll выбирает только bulk-eligible', () => {
    const page = useApprovalsPage()
    page.toggleSelectAll(true)
    expect(page.selectedCount.value).toBe(2)
    page.toggleSelectAll(false)
    expect(page.selectedCount.value).toBe(0)
  })

  it('toggleSelectAll ограничивает выборку лимитом партии и предупреждает', () => {
    // Ревью 2026-09-05: «выбрать все» при 51 документе отправляло всю выборку
    // и получало 422 от API (лимит схемы).
    const many = Array.from({ length: 25 }, (_, i) => doc(`d${i}`))
    listData.value = { items: many, total: many.length }
    const page = useApprovalsPage()
    page.toggleSelectAll(true)
    expect(page.selectedCount.value).toBe(BULK_APPROVE_MAX)
    expect(messageWarning).toHaveBeenCalled()
    page.toggleSelectAll(false)
    expect(page.selectedCount.value).toBe(0)
  })

  it('поиск фильтрует по номеру/контрагенту/типу', () => {
    const docs = [{ ...doc('a'), contractor: 'ООО Ромашка' }, doc('b')]
    listData.value = { items: docs, total: docs.length }
    const page = useApprovalsPage()
    page.search.value = 'РОМАШКА'
    expect(page.filteredItems.value.map((d) => (d as { guid: string }).guid)).toEqual(['a'])
    page.search.value = 'b'
    expect(page.filteredItems.value.map((d) => (d as { guid: string }).guid)).toEqual(['b'])
    page.search.value = '   '
    expect(page.filteredItems.value.length).toBe(2)
  })

  it('список отсортирован по сумме по убыванию; без суммы — в хвосте', () => {
    // Решение владельца 2026-09-06: 1С порядок списка не гарантирует —
    // крупные заказы сверху. Работаем с копией: кэш query не мутируем.
    const docs = [
      { ...doc('small'), amount: 7942.55 },
      { ...doc('big'), amount: 4480200 },
      { ...doc('none'), amount: null },
      { ...doc('mid'), amount: 31162.48 },
    ]
    listData.value = { items: docs, total: docs.length }
    const page = useApprovalsPage()
    expect(page.filteredItems.value.map((d) => d.guid)).toEqual(['big', 'mid', 'small', 'none'])
    // Исходный порядок данных не изменился
    expect(listData.value.items.map((d) => (d as { guid: string }).guid)).toEqual([
      'small',
      'big',
      'none',
      'mid',
    ])
  })

  it('bulkApproveSelected строит постоянный отчёт: документ → результат → причина', async () => {
    const page = useApprovalsPage()
    page.toggleSelected('a', true)
    page.toggleSelected('b', true)
    bulkMutate.mockResolvedValueOnce({
      results: [
        { uuid: 'a', ok: true, message: 'Согласовано' },
        { uuid: 'b', ok: false, message: 'ERP недоступна — документ не обрабатывался' },
      ],
      approved: 1,
      failed: 1,
    })
    await page.bulkApproveSelected()
    const report = page.bulkReport.value
    expect(report).toMatchObject({ approved: 1, failed: 1 })
    expect(report?.rows[0]).toMatchObject({ label: 'a', ok: true, message: 'Согласовано' })
    expect(report?.rows[1]).toMatchObject({
      label: 'b',
      ok: false,
      message: 'ERP недоступна — документ не обрабатывался',
    })
    // Тосты-счётчики заменены отчётом
    expect(messageWarning).not.toHaveBeenCalled()
    expect(messageSuccess).not.toHaveBeenCalled()
  })

  it('refresh обновляет очередь, не сбрасывая выбор (в отличие от reload)', async () => {
    const page = useApprovalsPage()
    page.toggleSelected('a', true)
    await page.refresh()
    expect(listRefetch).toHaveBeenCalled()
    expect(page.selectedCount.value).toBe(1)
  })

  it('uuid вне списка — сырой uuid в отчёте; dismissBulkReport скрывает отчёт', async () => {
    const page = useApprovalsPage()
    page.toggleSelected('a', true)
    bulkMutate.mockResolvedValueOnce({
      results: [{ uuid: 'ghost', ok: true, message: 'Согласовано' }],
      approved: 1,
      failed: 0,
    })
    await page.bulkApproveSelected()
    // 'ghost' отсутствует в очереди — в отчёте сырой uuid, а не номер
    expect(page.bulkReport.value?.rows[0]).toMatchObject({ label: 'ghost' })
    page.dismissBulkReport()
    expect(page.bulkReport.value).toBeNull()
  })

  it('retryDetail сбрасывает карточку и перезапрашивает', () => {
    const page = useApprovalsPage()
    page.openDrawer('g-1')
    page.retryDetail()
    expect(detailRefetch).toHaveBeenCalled()
    expect(page.detail.value).toBeNull()
  })

  it('ошибки списка и карточки отдаются наружу, а не маскируются под пустые', () => {
    listIsError.value = true
    detailIsError.value = true
    const page = useApprovalsPage()
    expect(page.listError.value).toBe(true)
    expect(page.detailError.value).toBe(false) // drawer закрыт
    page.openDrawer('g-1')
    expect(page.detailError.value).toBe(true)
  })

  it('toggleSelected добавляет и снимает', () => {
    const page = useApprovalsPage()
    page.toggleSelected('a', true)
    expect(page.selectedCount.value).toBe(1)
    page.toggleSelected('a', false)
    expect(page.selectedCount.value).toBe(0)
  })

  it('bulkApproveSelected: успех + сброс выбора + refetch', async () => {
    const page = useApprovalsPage()
    page.toggleSelectAll(true)
    await page.bulkApproveSelected()
    expect(bulkMutate).toHaveBeenCalledWith(['a', 'b'])
    expect(page.bulkReport.value).toMatchObject({ approved: 2, failed: 0 })
    expect(listRefetch).toHaveBeenCalled()
    expect(page.selectedCount.value).toBe(0)
  })

  it('bulkApproveSelected: часть с ошибками — отчёт с failed>0, без тоста', async () => {
    const page = useApprovalsPage()
    listData.value = { items: [doc('a')], total: 1 }
    page.toggleSelected('a', true)
    bulkMutate.mockResolvedValueOnce({
      results: [{ uuid: 'a', ok: false, message: 'отказ 1С' }],
      approved: 0,
      failed: 1,
    })
    await page.bulkApproveSelected()
    expect(page.bulkReport.value).toMatchObject({ approved: 0, failed: 1 })
    expect(messageWarning).not.toHaveBeenCalled()
  })

  it('quickApprove согласует без комментария и обновляет список', async () => {
    const page = useApprovalsPage()
    await page.quickApprove(doc('a') as never)
    expect(approveMutate).toHaveBeenCalledWith({ uuid: 'a', dto: { comment: '' } })
    expect(listRefetch).toHaveBeenCalled()
  })

  it('approveCurrent берёт uuid/комментарий из drawer-состояния', async () => {
    const page = useApprovalsPage()
    page.openDrawer('g-1')
    page.comment.value = '  ок  '
    await page.approveCurrent()
    expect(approveMutate).toHaveBeenCalledWith({
      uuid: 'g-1',
      dto: { comment: 'ок', manager_guid: null },
    })
    expect(messageSuccess).toHaveBeenCalled()
    expect(page.drawerUuid.value).toBeNull()
  })

  it('rejectCurrent без комментария — no-op', async () => {
    const page = useApprovalsPage()
    page.openDrawer('g-1')
    page.comment.value = '   '
    await page.rejectCurrent()
    expect(messageSuccess).not.toHaveBeenCalled()
  })

  it('ошибка действия — message.error', async () => {
    const page = useApprovalsPage()
    listData.value = { items: [doc('a')], total: 1 }
    page.toggleSelected('a', true)
    bulkMutate.mockRejectedValueOnce(new Error('boom'))
    await page.bulkApproveSelected()
    expect(messageError).toHaveBeenCalled()
  })

  it('closeDrawer очищает карточное состояние', () => {
    const page = useApprovalsPage()
    page.openDrawer('g-1')
    page.comment.value = 'x'
    page.closeDrawer()
    expect(page.drawerOpen.value).toBe(false)
    expect(page.detail.value).toBeNull()
    expect(page.comment.value).toBe('')
  })
})
