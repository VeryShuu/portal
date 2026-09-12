/**
 * Состояние сортировки списка заявок helpdesk.
 *
 * Сортировка серверная (ORDER BY в SQL, см. backend ``list_agent_tickets`` /
 * ``list_my_tickets``) — сортирует весь список по всем страницам, а не только
 * текущую страницу. Этот composable хранит выбранную колонку + направление и
 * отдаёт параметры для API-запроса.
 *
 * Цикл клика по заголовку: ``asc → desc → none → asc``. ``none`` = дефолтная
 * серверная сортировка (``last_activity_at DESC`` — свежие сверху), что
 * соответствует «нет активной сортировки». Это позволяет пользователю вернуться
 * к виду по умолчанию третьим кликом (как в почтовых клиентах/OTRS).
 *
 * Не персистится в localStorage сознательно: сортировка — оперативное
 * состояние просмотра, при перезагрузке/возвращении в инбокс логично видеть
 * свежие заявки сверху (дефолт), а не «тот же порядок, что неделю назад».
 */
import { computed, ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { HelpdeskColumnId } from './useHelpdeskInboxColumns'

export type SortDirection = 'asc' | 'desc'

export interface SortParams {
  /** Поле сортировки (null = серверный дефолт last_activity_at DESC). */
  sort: HelpdeskColumnId | null
  order: SortDirection
}

/** Маппинг id колонки → имя поля бэкенда (параметр ``sort`` в GET /tickets). */
export const SORT_FIELD_MAP: Record<HelpdeskColumnId, string> = {
  number: 'number',
  status: 'status',
  subject: 'subject',
  requester: 'requester',
  assignee: 'assignee',
  age: 'created_at',
  updated: 'last_activity_at',
}

export interface UseHelpdeskTicketSort {
  /** Текущий id колонки сортировки (null = дефолт). */
  sortColumn: Ref<HelpdeskColumnId | null>
  /** Текущее направление. */
  sortOrder: Ref<SortDirection>
  /** Параметры для API-запроса (sort/order или пусто, если дефолт). */
  apiParams: ComputedRef<{ sort?: string; order?: SortDirection }>
  /** Активна ли сортировка по колонке (и в каком направлении). */
  directionFor: (id: HelpdeskColumnId) => SortDirection | null
  /** Цикл клика: asc → desc → none → asc. */
  toggle: (id: HelpdeskColumnId) => void
}

export function useHelpdeskTicketSort(
  initialSort: HelpdeskColumnId | null = null,
  initialOrder: SortDirection = 'desc',
): UseHelpdeskTicketSort {
  const sortColumn = ref<HelpdeskColumnId | null>(initialSort)
  const sortOrder = ref<SortDirection>(initialOrder)

  const apiParams = computed(() => {
    if (sortColumn.value === null) return {}
    return {
      sort: SORT_FIELD_MAP[sortColumn.value],
      order: sortOrder.value,
    }
  })

  function directionFor(id: HelpdeskColumnId): SortDirection | null {
    if (sortColumn.value !== id) return null
    return sortOrder.value
  }

  function toggle(id: HelpdeskColumnId): void {
    if (sortColumn.value !== id) {
      // Новый столбец — стартуем asc (как в Naive UI DataTable по клику).
      sortColumn.value = id
      sortOrder.value = 'asc'
      return
    }
    // Тот же столбец: asc → desc → none.
    if (sortOrder.value === 'asc') {
      sortOrder.value = 'desc'
    } else if (sortOrder.value === 'desc') {
      sortColumn.value = null
      sortOrder.value = 'asc'
    }
  }

  return { sortColumn, sortOrder, apiParams, directionFor, toggle }
}
