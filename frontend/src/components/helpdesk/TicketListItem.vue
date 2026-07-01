<template>
  <div
    class="ticket-row"
    :class="{ 'ticket-row--agent': agentMode }"
    role="button"
    tabindex="0"
    @click="$emit('open', ticket.id)"
    @keydown.enter="$emit('open', ticket.id)"
    @keydown.space.prevent="$emit('open', ticket.id)"
  >
    <span class="ticket-row__cell ticket-row__num">#{{ ticket.number }}</span>
    <span class="ticket-row__cell ticket-row__status">
      <TicketStatusBadge :status="ticket.status" />
    </span>
    <span class="ticket-row__cell ticket-row__subject">{{ ticket.subject }}</span>
    <span
      v-if="agentMode"
      class="ticket-row__cell ticket-row__requester"
      :title="ticket.requester_name ?? ticket.requester_email"
    >
      {{ ticket.requester_name ?? ticket.requester_email }}
    </span>
    <span class="ticket-row__cell ticket-row__assignee">
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
    <span class="ticket-row__cell ticket-row__date">{{ formatDate(ticket.last_activity_at) }}</span>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton } from 'naive-ui'
import TicketStatusBadge from './TicketStatusBadge.vue'
import type { HelpdeskTicketListItem } from '../../api/helpdesk'

defineProps<{
  ticket: HelpdeskTicketListItem
  agentMode?: boolean
  taking?: boolean
}>()

defineEmits<{
  open: [id: string]
  take: [id: string]
}>()

const { t } = useI18n()

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
/* Agent view: # | State | Subject | Requester | Owner | Updated (6 cols)
   User view: # | State | Subject | Assignee | Updated (5 cols, no requester) */
.ticket-row {
  display: grid;
  grid-template-columns: 56px 92px minmax(0, 1fr) 150px 104px;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  transition: background 0.12s ease;
  outline: none;
}
.ticket-row--agent {
  grid-template-columns: 56px 92px minmax(0, 1fr) 150px 150px 104px;
}
.ticket-row:hover,
.ticket-row:focus-visible {
  background: var(--color-bg-muted);
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
.ticket-row__date {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
  justify-self: end;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.ticket-row__muted {
  color: var(--color-text-muted);
}

@media (max-width: 720px) {
  /* Stack into a compact two-line card on narrow viewports. */
  .ticket-row,
  .ticket-row--agent {
    grid-template-columns: auto 1fr auto;
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
  .ticket-row__date { grid-area: date; text-align: right; }
}
</style>
