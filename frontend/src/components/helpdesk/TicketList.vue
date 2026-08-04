<template>
  <div
    class="ticket-table"
    :class="{ 'ticket-table--has-settings': isAgent }"
  >
    <div
      ref="headEl"
      class="ticket-table__head"
      :class="{ 'ticket-table__head--sortable': isAgent }"
      :style="{ gridTemplateColumns: gridTemplate }"
    >
      <span
        v-for="col in visibleColumns"
        :key="col.id"
        :data-column-id="col.id"
        class="ticket-table__th"
        :class="{
          'ticket-table__th--fixed': col.fixed,
          'ticket-table__th--draggable': isAgent && !col.fixed,
          'ticket-table__th--end': col.align === 'end',
          'ticket-table__th--sortable-col': col.sortable,
          'ticket-table__th--active': col.sortable && directionFor(col.id) !== null,
        }"
        :role="col.sortable ? 'button' : undefined"
        :tabindex="col.sortable ? 0 : undefined"
        :aria-sort="ariaSort(col.id)"
        :title="col.sortable ? sortHint(col.id) : undefined"
        @click="col.sortable ? onSortClick(col.id) : undefined"
        @keydown.enter.prevent="col.sortable ? onSortClick(col.id) : undefined"
        @keydown.space.prevent="col.sortable ? onSortClick(col.id) : undefined"
      >
        <span class="ticket-table__th-label">{{ t(col.labelKey) }}</span>
        <span
          v-if="col.sortable"
          class="ticket-table__sort-indicator"
          :class="`ticket-table__sort-indicator--${directionFor(col.id) ?? 'none'}`"
          aria-hidden="true"
        >{{ sortGlyph(col.id) }}</span>
        <span
          v-if="isAgent && !col.fixed"
          class="ticket-table__grip"
          :title="t('helpdesk.dragColumnHint')"
          @click.stop
          @keydown.stop
        >⠿</span>
      </span>
    </div>
    <!-- «Шестерёнка» настроек колонок — вне grid-flow (absolute), чтобы не ломать
         выравнивание шапки и строк (раньше была 8-й grid-ячейкой → сдвигала все
         колонки после subject на 40px влево относительно данных). -->
    <div
      v-if="isAgent"
      class="ticket-table__settings"
    >
      <n-popover
        trigger="click"
        placement="bottom-end"
        :width="260"
      >
        <template #trigger>
          <n-button
            quaternary
            circle
            size="tiny"
            :title="t('helpdesk.columnsSettings')"
          >
            <template #icon>
              <n-icon><component :is="OptionsOutline" /></n-icon>
            </template>
          </n-button>
        </template>
        <div class="col-settings">
          <div class="col-settings__title">
            {{ t('helpdesk.columnsShowHide') }}
          </div>
          <div
            v-for="col in togglableColumns"
            :key="col.id"
            class="col-settings__row"
          >
            <n-checkbox
              :checked="!state.hidden.includes(col.id)"
              @update:checked="toggleColumn(col.id)"
            >
              {{ t(col.labelKey) }}
            </n-checkbox>
          </div>
          <div class="col-settings__footer">
            <n-button
              size="tiny"
              quaternary
              @click="resetColumns"
            >
              {{ t('helpdesk.columnsReset') }}
            </n-button>
          </div>
        </div>
      </n-popover>
    </div>
    <div class="ticket-table__body">
      <TicketListItem
        v-for="ticket in items"
        :key="ticket.id"
        :ticket="ticket"
        :visible-columns="visibleColumns"
        :grid-template="gridTemplate"
        :agent-mode="isAgent"
        :taking="takingId === ticket.id"
        @open="$emit('open', $event)"
        @take="$emit('take', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, useTemplateRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import Sortable from 'sortablejs'
import { NPopover, NButton, NIcon, NCheckbox } from 'naive-ui'
import { OptionsOutline } from '@vicons/ionicons5'
import TicketListItem from './TicketListItem.vue'
import {
  useHelpdeskInboxColumns,
  type HelpdeskColumnId,
  type HelpdeskColumnMode,
} from '../../composables/useHelpdeskInboxColumns'
import type { SortDirection } from '../../composables/useHelpdeskTicketSort'
import type { HelpdeskTicketListItem } from '../../api/helpdesk'

const props = defineProps<{
  items: HelpdeskTicketListItem[]
  /** id тикета, для которого сейчас идёт take-запрос (показывает спиннер). */
  takingId?: string | null
  /** Пресет колонок: ``'agent'`` (полный, настраиваемый) / ``'user'`` (упрощённый). */
  mode?: HelpdeskColumnMode
  /** Текущая колонка серверной сортировки (null = дефолт). */
  sortColumn?: HelpdeskColumnId | null
  /** Текущее направление сортировки. */
  sortOrder?: SortDirection
}>()

const emit = defineEmits<{
  open: [id: string]
  take: [id: string]
  /** Клик по сортируемому заголовку (страница обновит server-state запроса). */
  sort: [id: HelpdeskColumnId]
}>()

const { t } = useI18n()
const mode = computed(() => props.mode ?? 'agent')
const isAgent = computed(() => mode.value === 'agent')
const { state, visibleColumns, gridTemplate, togglableColumns, reorderColumn, toggleColumn, resetColumns } =
  useHelpdeskInboxColumns(mode.value)

// ── Сортировка: состояние живёт в странице (server-state запроса), компонент —
// чисто презентационный. Клик по заголовку эмитит ``sort``; индикатор/aria
// считаются из props.sortColumn/sortOrder через directionFor-прокси.
const sortColumnRef = computed(() => props.sortColumn ?? null)
const sortOrderRef = computed<SortDirection>(() => props.sortOrder ?? 'desc')

function directionFor(id: HelpdeskColumnId): SortDirection | null {
  return sortColumnRef.value === id ? sortOrderRef.value : null
}

function sortGlyph(id: HelpdeskColumnId): string {
  const dir = directionFor(id)
  if (dir === 'asc') return '▲'
  if (dir === 'desc') return '▼'
  return '↕'
}

function ariaSort(id: HelpdeskColumnId): 'ascending' | 'descending' | 'none' | undefined {
  const dir = directionFor(id)
  if (dir === 'asc') return 'ascending'
  if (dir === 'desc') return 'descending'
  return dir === null && sortColumnRef.value === null ? 'none' : undefined
}

function sortHint(id: HelpdeskColumnId): string {
  const dir = directionFor(id)
  if (dir === null) return t('helpdesk.sortHintNone')
  if (dir === 'asc') return t('helpdesk.sortHintAsc')
  return t('helpdesk.sortHintDesc')
}

function onSortClick(id: HelpdeskColumnId): void {
  emit('sort', id)
}

// ── Drag-and-drop порядка колонок (только в агентском режиме) ────────────────
// sortablejs физически двигает DOM-узлы шапки, но порядок рендера определяется
// реактивным ``state.order``. Поэтому после onEnd: (1) читаем итоговый порядок
// колонок из DOM, чтобы определить ``beforeId`` (сосед справа от moved);
// (2) возвращаем DOM к исходному виду — Vue перекроет ре-рендер из state;
// (3) мутируем state через ``reorderColumn`` — паттерн проекта (см.
// useSortableGroups). handle = «гrip»-иконка, чтобы клик по заголовку (сортировка)
// не запускал перетаскивание — две разные операции на одном заголовке.
const headEl = useTemplateRef<HTMLElement>('headEl')
let sortableInstance: Sortable | null = null

function domColumnOrder(): HelpdeskColumnId[] {
  const root = headEl.value
  if (!root) return visibleColumns.value.map((c) => c.id)
  const nodes = root.querySelectorAll<HTMLElement>('[data-column-id]')
  return Array.from(nodes).map((el) => el.dataset.columnId as HelpdeskColumnId)
}

function teardownSortable() {
  if (sortableInstance) {
    sortableInstance.destroy()
    sortableInstance = null
  }
}

function setupSortable() {
  if (sortableInstance || !headEl.value) return
  sortableInstance = Sortable.create(headEl.value, {
    handle: '.ticket-table__grip',
    animation: 150,
    ghostClass: 'ticket-table__ghost',
    chosenClass: 'ticket-table__chosen',
    dragClass: 'ticket-table__drag',
    draggable: '.ticket-table__th--draggable',
    filter: '.ticket-table__settings',
    onEnd(evt) {
      const moved = evt.item
      const parent = evt.to
      // (1) Пока DOM в переставленном состоянии — фиксируем новый порядок и
      // соседа справа от moved (это и есть beforeId для reorderColumn).
      const movedId = moved?.dataset.columnId as HelpdeskColumnId | undefined
      const order = domColumnOrder()
      let beforeId: HelpdeskColumnId | null = null
      if (movedId) {
        const idx = order.indexOf(movedId)
        if (idx >= 0 && idx + 1 < order.length) beforeId = order[idx + 1] ?? null
      }
      // (2) Revert DOM: вставляем moved обратно на oldIndex — источник истины
      // это state, Vue сам перерисует.
      if (moved && parent && evt.oldIndex != null) {
        const refNode = parent.children[evt.oldIndex] ?? null
        if (refNode) parent.insertBefore(moved, refNode)
        else parent.appendChild(moved)
      }
      // (3) Мутируем state (persist → localStorage).
      if (movedId) reorderColumn(movedId, beforeId)
    },
  })
}

// Первичная инициализация DnD — только после mount (headEl.value доступен).
// watch с immediate:true не годится: в setup() DOM ещё не смонтирован → headEl
// === null → ранний return из setupSortable → DnD не создавался (баг).
onMounted(() => {
  if (isAgent.value) setupSortable()
})

watch(
  () => isAgent.value,
  (enabled) => {
    if (enabled) setupSortable()
    else teardownSortable()
  },
)

onBeforeUnmount(teardownSortable)
</script>

<style scoped>
.ticket-table {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-surface);
  position: relative; /* для absolute-позиционирования «шестерёнки» */
}
.ticket-table__head {
  display: grid;
  gap: 12px;
  padding: 8px 14px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
  background: var(--color-bg-muted);
  border-bottom: 1px solid var(--color-border);
  align-items: center;
}
/* Агентский режим (есть «шестерёнка»): справа отступ у шапки и строк
   одинаковый (38px), чтобы последняя колонка не налезала на кнопку и шапка
   выравнивалась со строками по grid. User-режим — без шестерёнки, padding
   отсутствует (иначе рассинхрон шапка/строка). Класс на корневом .ticket-table. */
.ticket-table--has-settings .ticket-table__head,
.ticket-table--has-settings .ticket-table__body .ticket-row {
  padding-right: 38px;
}
.ticket-table__th {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
/* Все заголовки и данные выровнены по левому краю единообразно (как в OTRS).
   Раньше у updated было align:end (дата вправо) — убрано: рассинхрон с другими
   колонками и заголовком. ``font-variant-numeric: tabular-nums`` на дате даёт
   ровные столбцы цифр без правого выравнивания. */
.ticket-table__th-label {
  /* Заголовки столбцов не должны обрезаться (ellipsis) — это糟糕 UX, агент всегда
     видит полное название колонки. ``overflow: visible`` + ``nowrap``;
     ширина колонки подбирается так, чтобы вмещать заголовок (COLUMN_META). */
  white-space: nowrap;
}
/* Сортируемые заголовки — кликабельны, с hover-подсветкой и индикатором. */
.ticket-table__th--sortable-col {
  cursor: pointer;
  user-select: none;
}
.ticket-table__th--sortable-col:hover {
  color: var(--color-text);
}
.ticket-table__sort-indicator {
  font-size: 10px;
  line-height: 1;
  opacity: 0.45;
  flex-shrink: 0;
}
.ticket-table__th--active .ticket-table__sort-indicator {
  opacity: 1;
  color: var(--color-brand, #143a66);
}
.ticket-table__th--sortable-col:hover .ticket-table__sort-indicator {
  opacity: 0.8;
}
.ticket-table__head--sortable .ticket-table__th--draggable {
  cursor: grab;
}
.ticket-table__head--sortable .ticket-table__th--draggable:active {
  cursor: grabbing;
}
.ticket-table__grip {
  cursor: grab;
  color: var(--color-text-muted);
  opacity: 0.4;
  font-size: 13px;
  line-height: 1;
  user-select: none;
  flex-shrink: 0;
}
.ticket-table__head--sortable .ticket-table__th--draggable:hover .ticket-table__grip {
  opacity: 0.9;
}
/* «Шестерёнка» настроек колонок — absolute в правом верхнем углу таблицы,
   вне grid-flow шапки. Раньше была grid-ячейкой → ломала выравнивание колонок.
   ``top`` привязан к высоте шапки (padding-top 8px + ~половина строки), чтобы
   кнопка стояла на одной горизонтали с grip «⠿» и индикатором сортировки. */
.ticket-table__settings {
  position: absolute;
  top: 6px;
  right: 8px;
  z-index: 1;
  display: flex;
  align-items: center;
}
.ticket-table__settings :deep(.n-button) {
  /* Размер иконки на уровне grip «⠿» (13px), чтобы не выглядела крупнее. */
  font-size: 14px;
}
/* ghost/clone-состояния sortablejs — лёгкая подсветка перетаскиваемой колонки */
.ticket-table__ghost {
  opacity: 0.4;
}
.ticket-table__chosen {
  opacity: 0.85;
}
.ticket-table__drag {
  background: var(--color-surface);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  border-radius: 4px;
  padding: 2px 6px;
}
.ticket-table__body :deep(.ticket-row:last-child) {
  border-bottom: none;
}
/* Меню «шестерёнки» */
.col-settings {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.col-settings__title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
  margin-bottom: 4px;
}
.col-settings__row {
  display: flex;
  align-items: center;
}
.col-settings__footer {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--color-border);
  display: flex;
  justify-content: flex-end;
}
</style>
