/**
 * Оркестрация страницы «Согласование документов» (docs/approvals.md).
 *
 * Список 1С приходит целиком (пагинации нет); выбор чекбоксами + массовое
 * согласование; карточка — в NDrawer. Бизнес-правила 1:1 со старым PHP:
 * отклонение только с непустым комментарием; документы с
 * requires_manager из массового согласования исключены.
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { parseApiError } from '../../utils/parseApiError'
import type { ApprovalDocument, ApprovalDocumentDetail } from '../../api/approvals'
import { BULK_APPROVE_MAX } from '../../api/approvals'
import {
  useApprovalsQuery,
  useApproveMutation,
  useApprovalDetailQuery,
  useBulkApproveMutation,
  useRejectMutation,
} from '../../queries/approvals'

/** Строка постоянного отчёта массового согласования: документ → результат → причина. */
export interface BulkApproveReportRow {
  uuid: string
  /** Номер документа (или сырой uuid, если документ исчез из очереди). */
  label: string
  /** Контрагент/подпись второй строкой. */
  sub: string
  ok: boolean
  message: string
}

export interface BulkApproveReport {
  approved: number
  failed: number
  rows: BulkApproveReportRow[]
}

export function useApprovalsPage() {
  const { t } = useI18n()
  const message = useMessage()

  const listQuery = useApprovalsQuery()
  const approveMut = useApproveMutation()
  const rejectMut = useRejectMutation()
  const bulkMut = useBulkApproveMutation()

  const selected = ref<Set<string>>(new Set())
  const drawerUuid = ref<string | null>(null)
  const detail = ref<ApprovalDocumentDetail | null>(null)
  const comment = ref('')
  const managerGuid = ref<string | null>(null)
  const actionRunning = ref(false)
  const search = ref('')
  const bulkReport = ref<BulkApproveReport | null>(null)

  const detailQuery = useApprovalDetailQuery(() => drawerUuid.value)
  watch(detailQuery.data, (d) => {
    if (!d) return
    detail.value = d
    comment.value = ''
    managerGuid.value = null
  })

  const items = computed<ApprovalDocument[]>(() => listQuery.data.value?.items ?? [])
  const loading = computed(() => listQuery.isLoading.value)
  // Ошибка списка ≠ пустая очередь: явный error-state с повтором (ревью 2026-09-05).
  const listError = computed(() => listQuery.isError.value)
  /** Фоновое обновление (кнопка «Обновить»), в отличие от первого loading. */
  const refreshing = computed(() => listQuery.isFetching.value && !listQuery.isLoading.value)
  // isLoading (а не «нет данных»): при ошибке карточки спиннер обязан
  // остановиться, иначе крутится вечно (ревью 2026-09-05).
  const detailLoading = computed(() => drawerUuid.value !== null && detailQuery.isLoading.value)
  const detailError = computed(() => drawerUuid.value !== null && detailQuery.isError.value)
  const drawerOpen = computed({
    get: () => drawerUuid.value !== null,
    set: (v: boolean) => {
      if (!v) closeDrawer()
    },
  })

  /**
   * Клиентский поиск по номеру/контрагенту/типу + сортировка по сумме
   * документа по убыванию (решение владельца 2026-09-06: крупные заказы
   * сверху; 1С порядок не гарантирует). Документы без суммы — в хвосте.
   * Работает с копией: кэш TanStack Query мутировать нельзя.
   */
  const filteredItems = computed<ApprovalDocument[]>(() => {
    const q = search.value.trim().toLowerCase()
    const matched = q
      ? items.value.filter(
          (d) =>
            d.number.toLowerCase().includes(q) ||
            (d.contractor ?? '').toLowerCase().includes(q) ||
            d.doc_type.toLowerCase().includes(q),
        )
      : items.value
    return [...matched].sort(
      (a, b) =>
        (b.amount ?? Number.NEGATIVE_INFINITY) - (a.amount ?? Number.NEGATIVE_INFINITY),
    )
  })

  /**
   * Доступны для массового согласования: не требуют ответственного.
   * Внутренние заказы (has_prices=false) показываются информационно —
   * их согласование заблокировано до готовности функционала
   * (решение владельца, 2026-09-05).
   */
  const bulkEligible = computed(() =>
    filteredItems.value.filter((d) => !d.requires_manager && d.has_prices),
  )
  const selectedCount = computed(() => selected.value.size)
  const allSelected = computed(
    () =>
      bulkEligible.value.length > 0 && bulkEligible.value.every((d) => selected.value.has(d.guid)),
  )

  function toggleSelected(guid: string, value: boolean) {
    const next = new Set(selected.value)
    if (value) next.add(guid)
    else next.delete(guid)
    selected.value = next
  }

  function toggleSelectAll(value: boolean) {
    if (!value) {
      selected.value = new Set()
      return
    }
    const eligible = bulkEligible.value
    // Лимит партии (зеркало BULK_APPROVE_MAX на бэке): иначе «выбрать все»
    // отправляло выборку, которую API отвергал по 422 (ревью 2026-09-05).
    selected.value = new Set(eligible.slice(0, BULK_APPROVE_MAX).map((d) => d.guid))
    if (eligible.length > BULK_APPROVE_MAX) {
      message.warning(t('approvals.bulkCapped', { max: BULK_APPROVE_MAX, total: eligible.length }))
    }
  }

  function openDrawer(uuid: string) {
    detail.value = null
    drawerUuid.value = uuid
  }

  function closeDrawer() {
    drawerUuid.value = null
    detail.value = null
    comment.value = ''
    managerGuid.value = null
  }

  /** Повтор карточки после ошибки: сперва сбрасываем устаревшее состояние. */
  function retryDetail() {
    detail.value = null
    void detailQuery.refetch()
  }

  async function reload() {
    await listQuery.refetch()
    selected.value = new Set()
  }

  /** Ручное обновление очереди: выбор сохраняем — bulk перепроверит принадлежность. */
  async function refresh() {
    await listQuery.refetch()
  }

  async function approveCurrent() {
    const uuid = drawerUuid.value
    if (!uuid) return
    actionRunning.value = true
    try {
      const res = await approveMut.mutateAsync({
        uuid,
        dto: { comment: comment.value.trim(), manager_guid: managerGuid.value },
      })
      message.success(res.message || t('approvals.approved'))
      await reload()
      closeDrawer()
    } catch (e) {
      message.error(parseApiError(e, t))
    } finally {
      actionRunning.value = false
    }
  }

  /** Быстрое согласование из списка: без комментария и ответственного. */
  async function quickApprove(doc: ApprovalDocument) {
    actionRunning.value = true
    try {
      const res = await approveMut.mutateAsync({ uuid: doc.guid, dto: { comment: '' } })
      message.success(res.message || t('approvals.approved'))
      await reload()
    } catch (e) {
      message.error(parseApiError(e, t))
    } finally {
      actionRunning.value = false
    }
  }

  async function rejectCurrent() {
    const uuid = drawerUuid.value
    const text = comment.value.trim()
    if (!uuid || !text) return
    actionRunning.value = true
    try {
      const res = await rejectMut.mutateAsync({ uuid, dto: { comment: text } })
      message.success(res.message || t('approvals.rejected'))
      await reload()
      closeDrawer()
    } catch (e) {
      message.error(parseApiError(e, t))
    } finally {
      actionRunning.value = false
    }
  }

  async function bulkApproveSelected() {
    const uuids = [...selected.value]
    if (!uuids.length) return
    actionRunning.value = true
    try {
      const res = await bulkMut.mutateAsync(uuids)
      // Постоянный отчёт (документ → результат → причина отказа) вместо
      // одноразового тоста-счётчика: backend возвращает по-документные
      // результаты, пользователь должен видеть судьбу каждого документа
      // (ревью 2026-09-05). Реквизиты маппим ДО refetch — согласованные
      // документы исчезнут из очереди.
      const byUuid = new Map(items.value.map((d) => [d.guid, d]))
      bulkReport.value = {
        approved: res.approved,
        failed: res.failed,
        rows: res.results.map((r) => {
          const doc = byUuid.get(r.uuid)
          return {
            uuid: r.uuid,
            label: doc?.number || r.uuid,
            sub: doc?.contractor ?? '',
            ok: r.ok,
            message: r.message,
          }
        }),
      }
      await reload()
    } catch (e) {
      message.error(parseApiError(e, t))
    } finally {
      actionRunning.value = false
    }
  }

  function dismissBulkReport() {
    bulkReport.value = null
  }

  return {
    // список
    items,
    filteredItems,
    loading,
    listError,
    refreshing,
    search,
    refresh,
    selected,
    selectedCount,
    allSelected,
    bulkEligible,
    toggleSelected,
    toggleSelectAll,
    reload,
    bulkApproveSelected,
    bulkReport,
    dismissBulkReport,
    quickApprove,
    actionRunning,
    // карточка
    drawerOpen,
    drawerUuid,
    detail,
    detailLoading,
    detailError,
    retryDetail,
    comment,
    managerGuid,
    openDrawer,
    closeDrawer,
    approveCurrent,
    rejectCurrent,
  }
}
