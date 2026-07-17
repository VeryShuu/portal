<template>
  <div class="ticket-table">
    <div class="ticket-table__head ticket-table__head--agent">
      <span>{{ t('helpdesk.columnNumber') }}</span>
      <span>{{ t('helpdesk.columnState') }}</span>
      <span>{{ t('helpdesk.columnSubject') }}</span>
      <span>{{ t('helpdesk.columnRequester') }}</span>
      <span>{{ t('helpdesk.columnOwner') }}</span>
      <span>{{ t('helpdesk.columnUpdated') }}</span>
    </div>
    <div class="ticket-table__body">
      <TicketListItem
        v-for="ticket in items"
        :key="ticket.id"
        :ticket="ticket"
        agent-mode
        :taking="takingId === ticket.id"
        @open="$emit('open', $event)"
        @take="$emit('take', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import TicketListItem from './TicketListItem.vue'
import type { HelpdeskTicketListItem } from '../../api/helpdesk'

defineProps<{
  items: HelpdeskTicketListItem[]
  /** id тикета, для которого сейчас идёт take-запрос (показывает спиннер). */
  takingId?: string | null
}>()

defineEmits<{
  open: [id: string]
  take: [id: string]
}>()

const { t } = useI18n()
</script>

<style scoped>
.ticket-table {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-surface);
}
.ticket-table__head {
  display: grid;
  grid-template-columns: 56px 92px minmax(0, 1fr) 150px 150px 104px;
  gap: 12px;
  padding: 8px 14px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
  background: var(--color-bg-muted);
  border-bottom: 1px solid var(--color-border);
}
.ticket-table__head--agent span:last-child {
  text-align: right;
}
.ticket-table__body :deep(.ticket-row:last-child) {
  border-bottom: none;
}
</style>
