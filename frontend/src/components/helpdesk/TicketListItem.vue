<template>
  <div
    class="ticket-row"
    :class="{ 'ticket-row--agent': agentMode, 'ticket-row--unread': ticket.unread }"
    :title="ticket.unread ? t('helpdesk.hasUnread') : undefined"
    role="button"
    tabindex="0"
    :style="{ gridTemplateColumns: gridTemplate }"
    @click="$emit('open', ticket.id)"
    @keydown.enter="$emit('open', ticket.id)"
    @keydown.space.prevent="$emit('open', ticket.id)"
  >
    <template
      v-for="col in visibleColumns"
      :key="col.id"
    >
      <!-- Номер тикета + индикатор непрочитанного -->
      <span
        v-if="col.id === 'number'"
        class="ticket-row__cell ticket-row__num"
      >
        <span
          v-if="ticket.unread"
          class="ticket-row__unread-dot"
          :aria-label="t('helpdesk.hasUnread')"
        />
        #{{ ticket.number }}
      </span>
      <!-- Статус -->
      <span
        v-else-if="col.id === 'status'"
        class="ticket-row__cell ticket-row__status"
      >
        <TicketStatusBadge :status="ticket.status" />
      </span>
      <!-- Тема (FIXED — всегда видна) -->
      <span
        v-else-if="col.id === 'subject'"
        class="ticket-row__cell ticket-row__subject"
      >{{ ticket.subject }}</span>
      <!-- Инициатор (только агентский режим) -->
      <span
        v-else-if="col.id === 'requester'"
        class="ticket-row__cell ticket-row__requester"
        :title="ticket.requester_name ?? ticket.requester_email"
      >
        {{ ticket.requester_name ?? ticket.requester_email }}
      </span>
      <!-- Ответственный / кнопка «Взять» -->
      <span
        v-else-if="col.id === 'assignee'"
        class="ticket-row__cell ticket-row__assignee"
      >
        <span
          v-if="ticket.assignee_name"
          :title="ticket.assignee_name"
        >{{ ticket.assignee_name }}</span>
        <n-button
          v-else-if="agentMode"
          size="tiny"
          type="primary"
          ghost
          :loading="taking"
          @click.stop="$emit('take', ticket.id)"
        >
          {{ t('helpdesk.take') }}
        </n-button>
        <span
          v-else
          class="ticket-row__muted"
        >—</span>
      </span>
      <!-- Возраст заявки (дни от created_at; считается на фронте) -->
      <span
        v-else-if="col.id === 'age'"
        class="ticket-row__cell ticket-row__age"
        :class="{ 'ticket-row__age--stale': ageDays >= STALE_DAYS }"
        :title="t('helpdesk.ageSinceCreated')"
      >{{ t('helpdesk.ageDays', ageDays) }}</span>
      <!-- Обновлено (last_activity_at) -->
      <span
        v-else-if="col.id === 'updated'"
        class="ticket-row__cell ticket-row__date"
      >{{ formatDate(ticket.last_activity_at) }}</span>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import TicketStatusBadge from './TicketStatusBadge.vue'
import { ticketAgeDays } from '../../utils/helpdeskTicketAge'
import type { HelpdeskColumnMeta } from '../../composables/useHelpdeskInboxColumns'
import type { HelpdeskTicketListItem } from '../../api/helpdesk'

const props = defineProps<{
  ticket: HelpdeskTicketListItem
  /** Колонки для рендера (от TicketList — единый источник истины). */
  visibleColumns: HelpdeskColumnMeta[]
  /** CSS grid-template-columns — должен совпадать с шапкой TicketList. */
  gridTemplate: string
  agentMode?: boolean
  taking?: boolean
}>()

defineEmits<{
  open: [id: string]
  take: [id: string]
}>()

const { t } = useI18n()

// «Возраст» заявки в днях (полные сутки от created_at). Бэкенд уже отдаёт
// created_at в TicketListItemOut, поэтому колонка считается на фронте без
// правок API. Функция вынесена в utils/helpdeskTicketAge для unit-тестов.
const ageDays = computed(() => ticketAgeDays(props.ticket.created_at))

/** Порог «зависшей» заявки (дн.) — лёгкая визуальная подсветка. */
const STALE_DAYS = 7

function formatDate(iso: string): string {
  // Fixed-width numeric format so the date column aligns perfectly across
  // rows regardless of locale month-abbreviation length (ru "мая"=3 vs
  // "февр."=5 would otherwise rag the column). "DD.MM HH:MM" is always 11 chars.
  const d = new Date(iso)
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${dd}.${mm} ${hh}:${mi}`
}
</script>

<style scoped>
/* Шапка и строка рендерятся из одного reactive-state (useHelpdeskInboxColumns),
   поэтому grid-template-columns задаётся инлайн из props/gridTemplate — все
   строки таблицы выровнены с шапкой. Колонки (Agent): # | State | Subject |
   Requester | Owner | Age | Updated. Subject = flex (minmax(0,1fr)). */
.ticket-row {
  display: grid;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  transition: background 0.12s ease;
  outline: none;
}
.ticket-row:hover,
.ticket-row:focus-visible {
  background: var(--color-bg-muted);
}
/* Непрочитанная заявка (есть новые ответы заявителя, которые агент ещё не
   открывал — миграция 080). Единый визуальный язык с NotificationsDropdown:
   полупрозрачный фон + красная точка перед номером. Hover сохраняет акцент,
   но чуть сильнее — иначе unread-строка теряет подсветку при наведении. */
.ticket-row--unread {
  background: rgba(20, 58, 102, 0.05);
}
.ticket-row--unread:hover,
.ticket-row--unread:focus-visible {
  background: rgba(20, 58, 102, 0.1);
}
[data-theme='dark'] .ticket-row--unread {
  background: rgba(255, 255, 255, 0.05);
}
[data-theme='dark'] .ticket-row--unread:hover,
[data-theme='dark'] .ticket-row--unread:focus-visible {
  background: rgba(255, 255, 255, 0.1);
}
.ticket-row__unread-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  border-radius: 50%;
  background: var(--color-brand-red, #d8262c);
  vertical-align: middle;
  flex-shrink: 0;
}
.ticket-row--unread .ticket-row__subject {
  font-weight: 700;
}
.ticket-row--unread .ticket-row__num {
  color: var(--color-text);
}
.ticket-row__cell {
  min-width: 0;
}
.ticket-row__num {
  font-weight: 700;
  font-size: 13px;
  color: var(--color-text-secondary);
}
.ticket-row__status {
  display: flex;
}
.ticket-row__subject {
  font-weight: 500;
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ticket-row__requester,
.ticket-row__assignee {
  font-size: 13px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ticket-row__age {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
/* Зависшие заявки (>= STALE_DAYS) — приглушённый акцент, чтобы бросались
   в глаза при сканировании инбокса. Не красный (не ошибка), а амбер. */
.ticket-row__age--stale {
  color: var(--color-warning, #b07900);
  font-weight: 600;
}
.ticket-row__date {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.ticket-row__muted {
  color: var(--color-text-muted);
}

@media (max-width: 720px) {
  /* На узких экранах grid ломается — переключаемся на компактный двухстрочный
     вид, как в исходной версии. Порядок колонок сохраняется через
     grid-template-areas, но age здесь не показываем (экономим место). */
  .ticket-row {
    grid-template-columns: auto 1fr auto !important;
    grid-template-areas:
      "num status date"
      "subject subject subject"
      "requester assignee assignee";
    gap: 4px 10px;
    padding: 10px 14px;
  }
  .ticket-row__num { grid-area: num; }
  .ticket-row__status { grid-area: status; }
  .ticket-row__subject { grid-area: subject; }
  .ticket-row__requester { grid-area: requester; }
  .ticket-row__assignee { grid-area: assignee; }
  .ticket-row__age { display: none; }
  .ticket-row__date { grid-area: date; text-align: right; }
}
</style>
