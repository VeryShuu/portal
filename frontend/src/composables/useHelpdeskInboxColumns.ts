/**
 * Настраиваемые столбцы списков заявок helpdesk.
 *
 * Единый источник истины для шапки таблицы (``TicketList``) и строк
 * (``TicketListItem``): порядок, видимость и ширина колонок. ``TicketList``
 * создаёт один экземпляр composable и **прокидывает** видимые колонки +
 * ``gridTemplate`` в ``TicketListItem`` через props — строки чисто
 * презентационные, не дёргают composable сами (однонаправленный поток данных).
 *
 * Два пресета:
 *  - ``'agent'`` — полный набор (номер/статус/тема/инициатор/ответственный/
 *    возраст/обновлено), настраиваемый: агент меняет порядок (drag-and-drop),
 *    видимость и ширину колонок. Состояние персональное, хранится в
 *    ``localStorage`` (ключ ``helpdesk.inbox.columns``) по образцу
 *    ``helpdesk.inbox.scope``. Синхронизации между устройствами нет (сознательное
 *    упрощение, см. план фичи).
 *  - ``'user'`` — упрощённый фиксированный набор (номер/статус/тема/
 *    ответственный/обновлено), без колонок «инициатор»/«возраст» (заявителю
 *    не нужно видеть своё ФИО и «возраст» своей заявки). Не настраивается и не
 *    персистится — mutation-операции — no-op.
 *
 * Forward-compat: при появлении новых колонок старая запись в storage не должна
 * ломать UI. Поэтому ``loadState`` валидирует id'шники (неизвестные —
 * игнорируются) и дополняет недостающие дефолтные в конец.
 */
import { computed, reactive, readonly } from 'vue'
import type { ComputedRef, DeepReadonly } from 'vue'

export type HelpdeskColumnId =
  | 'number'
  | 'status'
  | 'subject'
  | 'requester'
  | 'assignee'
  | 'age'
  | 'updated'

export type HelpdeskColumnMode = 'agent' | 'user'

export interface HelpdeskColumnMeta {
  /** Идентификатор колонки — стабилен между релизами (storage-ключ). */
  id: HelpdeskColumnId
  /** i18n-ключ заголовка (полный, с неймспейсом ``helpdesk.``). */
  labelKey: string
  /** Ширина по умолчанию, px. Для ``subject`` игнорируется (flex). */
  defaultWidth: number
  /**
   * Колонку нельзя скрыть, переместить или сузить. ``subject`` — идентификатор
   * тикета, всегда на месте и видима.
   */
  fixed?: boolean
  /** Можно ли скрыть через меню «шестерёнки». FIXED-колонки — нет. */
  hideable?: boolean
  /** Горизонтальное выравнивание ячейки и заголовка. По умолчанию ``start``. */
  align?: 'start' | 'end'
  /** Разрешена ли серверная сортировка по этой колонке. */
  sortable?: boolean
}

/** Полный дескриптор каждой колонки (метаданные стабильны между пресетами). */
export const COLUMN_META: Record<HelpdeskColumnId, HelpdeskColumnMeta> = {
  number: {
    id: 'number',
    labelKey: 'helpdesk.columnNumber',
    defaultWidth: 56,
    hideable: false,
    sortable: true,
  },
  status: { id: 'status', labelKey: 'helpdesk.columnState', defaultWidth: 92, sortable: true },
  subject: {
    id: 'subject',
    labelKey: 'helpdesk.columnSubject',
    defaultWidth: 0,
    fixed: true,
    hideable: false,
  },
  requester: {
    id: 'requester',
    labelKey: 'helpdesk.columnRequester',
    defaultWidth: 200,
    sortable: true,
  },
  assignee: {
    id: 'assignee',
    labelKey: 'helpdesk.columnOwner',
    defaultWidth: 200,
    sortable: true,
  },
  age: { id: 'age', labelKey: 'helpdesk.columnAge', defaultWidth: 80, sortable: true },
  updated: {
    id: 'updated',
    labelKey: 'helpdesk.columnUpdated',
    defaultWidth: 104,
    align: 'end',
    sortable: true,
  },
}

/** Порядок колонок по умолчанию для каждого пресета. */
const PRESET_ORDER: Record<HelpdeskColumnMode, HelpdeskColumnId[]> = {
  agent: ['number', 'status', 'subject', 'requester', 'assignee', 'age', 'updated'],
  user: ['number', 'status', 'subject', 'assignee', 'updated'],
}

const STORAGE_KEY = 'helpdesk.inbox.columns'
const MIN_COLUMN_WIDTH = 48
const MAX_COLUMN_WIDTH = 600

interface ColumnState {
  order: HelpdeskColumnId[]
  hidden: HelpdeskColumnId[]
  widths: Record<HelpdeskColumnId, number>
}

interface StoredShape {
  order?: unknown
  hidden?: unknown
  widths?: unknown
}

function defaultWidthsFor(order: HelpdeskColumnId[]): Record<HelpdeskColumnId, number> {
  const widths = {} as Record<HelpdeskColumnId, number>
  for (const id of order) widths[id] = COLUMN_META[id].defaultWidth
  return widths
}

function isColumnId(value: unknown): value is HelpdeskColumnId {
  return typeof value === 'string' && value in COLUMN_META
}

function clampWidth(px: number): number {
  if (!Number.isFinite(px)) return 0
  return Math.max(MIN_COLUMN_WIDTH, Math.min(MAX_COLUMN_WIDTH, Math.round(px)))
}

/**
 * Восстановить agent-состояние из ``localStorage`` с защитой от повреждённых
 * данных. Только для пресета ``'agent'`` (``'user'`` не персистится).
 *
 * - Неизвестные id'шники (старая/будущая версия) — отбрасываются.
 * - Недостающие дефолтные id'шники — дополняются в конец (forward-compat).
 * - FIXED-колонку ``subject`` нельзя ни скрыть, ни убрать из порядка.
 * - Ширины берутся из storage, но валидируются диапазоном; для ``subject``
 *   (flex) ширина не хранится.
 */
export function loadAgentState(): ColumnState {
  const defaultOrder = PRESET_ORDER.agent
  const fallback: ColumnState = {
    order: [...defaultOrder],
    hidden: [],
    widths: defaultWidthsFor(defaultOrder),
  }
  if (typeof localStorage === 'undefined') return fallback
  let raw: string | null = null
  try {
    raw = localStorage.getItem(STORAGE_KEY)
  } catch {
    // localStorage может быть недоступен (private mode / sandbox) — работаем
    // с дефолтами, без бросания.
    return fallback
  }
  if (!raw) return fallback

  let parsed: StoredShape
  try {
    parsed = JSON.parse(raw) as StoredShape
  } catch {
    return fallback
  }

  // Порядок: только известные id, с дополнением недостающих дефолтных в конец.
  let order = fallback.order
  if (Array.isArray(parsed.order)) {
    const known = parsed.order.filter(isColumnId)
    const seen = new Set<HelpdeskColumnId>(known)
    const missing = defaultOrder.filter((id) => !seen.has(id))
    order = [...known, ...missing]
  }

  // Видимость: ``subject`` (FIXED) и не-hideable колонки нельзя скрыть;
  // неизвестные id игнорируются.
  let hidden = fallback.hidden
  if (Array.isArray(parsed.hidden)) {
    hidden = parsed.hidden.filter(
      (id): id is HelpdeskColumnId =>
        isColumnId(id) &&
        id !== 'subject' &&
        COLUMN_META[id].hideable !== false,
    )
  } else if (parsed.hidden === null) {
    hidden = []
  }

  // Ширины: валидация диапазона; flex-колонки (subject) не сохраняются.
  let widths = defaultWidthsFor(order)
  if (parsed.widths && typeof parsed.widths === 'object') {
    for (const id of order) {
      if (COLUMN_META[id].fixed) continue
      const raw = (parsed.widths as Record<string, unknown>)[id]
      if (typeof raw === 'number' && Number.isFinite(raw)) {
        widths[id] = clampWidth(raw)
      }
    }
  }

  return { order, hidden, widths }
}

function persist(state: ColumnState): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Квота превышена / private mode — настройки живут только в сессии.
  }
}

export interface UseHelpdeskInboxColumns {
  /** Все колонки пресета (включая скрытые) — для меню «шестерёнки». */
  columns: ComputedRef<HelpdeskColumnMeta[]>
  state: DeepReadonly<ColumnState>
  /** Колонки в порядке отображения (``order`` без скрытых). */
  visibleColumns: ComputedRef<HelpdeskColumnMeta[]>
  /** CSS-строка для ``grid-template-columns``. ``subject`` → flex. */
  gridTemplate: ComputedRef<string>
  /** Колонки, которые можно скрыть/показать (FIXED и hideable:false исключены). */
  togglableColumns: ComputedRef<HelpdeskColumnMeta[]>
  reorderColumn: (movedId: HelpdeskColumnId, beforeId: HelpdeskColumnId | null) => void
  toggleColumn: (id: HelpdeskColumnId) => void
  setColumnWidth: (id: HelpdeskColumnId, px: number) => void
  resetColumns: () => void
}

/**
 * @param mode ``'agent'`` — полный настраиваемый пресет с персистенцией;
 *   ``'user'`` — упрощённый фиксированный пресет (mutation-операции no-op).
 */
export function useHelpdeskInboxColumns(mode: HelpdeskColumnMode = 'agent'): UseHelpdeskInboxColumns {
  const defaultOrder = PRESET_ORDER[mode]

  // Agent-режим — реактивный state с персистенцией; user-режим — фикс. пресет
  // без скрытых колонок и без ширины (всё по умолчанию).
  const state =
    mode === 'agent'
      ? reactive<ColumnState>(loadAgentState())
      : reactive<ColumnState>({
          order: [...defaultOrder],
          hidden: [],
          widths: defaultWidthsFor(defaultOrder),
        })

  const columns = computed<HelpdeskColumnMeta[]>(() =>
    state.order.map((id) => COLUMN_META[id]),
  )

  const visibleColumns = computed<HelpdeskColumnMeta[]>(() =>
    state.order
      .map((id) => COLUMN_META[id])
      .filter((c) => c && !state.hidden.includes(c.id)),
  )

  const gridTemplate = computed<string>(() =>
    visibleColumns.value
      .map((c) => (c.fixed ? 'minmax(0, 1fr)' : `${state.widths[c.id] ?? c.defaultWidth}px`))
      .join(' '),
  )

  const togglableColumns = computed<HelpdeskColumnMeta[]>(() =>
    columns.value.filter((c) => c.fixed !== true && c.hideable !== false),
  )

  const writable = mode === 'agent'

  /**
   * Переместить колонку ``movedId`` так, чтобы она оказалась перед ``beforeId``
   * (или в конце, если ``beforeId === null``). Идентификаторы вместо индексов —
   * надёжнее при hidden-колонках и тестируемее в unit-тестах.
   */
  function reorderColumn(
    movedId: HelpdeskColumnId,
    beforeId: HelpdeskColumnId | null,
  ): void {
    if (!writable) return
    const meta = COLUMN_META[movedId]
    if (!meta || meta.fixed) return // subject нельзя двигать
    if (!state.order.includes(movedId)) return
    if (beforeId !== null) {
      if (!state.order.includes(beforeId)) return
      if (beforeId === movedId) return
    }
    const next = state.order.filter((id) => id !== movedId)
    const insertAt = beforeId === null ? next.length : next.indexOf(beforeId)
    if (insertAt < 0) return
    next.splice(insertAt, 0, movedId)
    state.order = next
    persist(state)
  }

  function toggleColumn(id: HelpdeskColumnId): void {
    if (!writable) return
    const meta = COLUMN_META[id]
    if (!meta || meta.fixed || meta.hideable === false) return
    if (state.hidden.includes(id)) {
      state.hidden = state.hidden.filter((x) => x !== id)
    } else {
      state.hidden = [...state.hidden, id]
    }
    persist(state)
  }

  function setColumnWidth(id: HelpdeskColumnId, px: number): void {
    if (!writable) return
    const meta = COLUMN_META[id]
    if (!meta || meta.fixed) return
    state.widths[id] = clampWidth(px)
    persist(state)
  }

  function resetColumns(): void {
    if (!writable) return
    state.order = [...defaultOrder]
    state.hidden = []
    state.widths = defaultWidthsFor(defaultOrder)
    persist(state)
  }

  return {
    columns,
    state: readonly(state) as DeepReadonly<ColumnState>,
    visibleColumns,
    gridTemplate,
    togglableColumns,
    reorderColumn,
    toggleColumn,
    setColumnWidth,
    resetColumns,
  }
}
