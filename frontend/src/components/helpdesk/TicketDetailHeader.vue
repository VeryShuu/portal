<template>
  <n-card class="ticket-header">
    <div class="ticket-header__top">
      <div class="ticket-header__idline">
        <span class="ticket-header__num">#{{ ticket.number }}</span>
        <TicketStatusBadge :status="ticket.status" />
        <n-tag
          v-if="ticket.source"
          size="tiny"
          :bordered="false"
        >
          {{ ticket.source }}
        </n-tag>
      </div>
      <div class="ticket-header__actions">
        <slot name="actions" />
      </div>
    </div>

    <h1 class="ticket-header__subject">
      {{ ticket.subject }}
    </h1>

    <dl class="ticket-header__meta">
      <div
        v-if="ticket.requester_name || ticket.requester_email"
        class="ticket-header__field"
      >
        <dt>{{ t('helpdesk.requester') }}</dt>
        <dd>
          <strong>{{ ticket.requester_name ?? ticket.requester_email }}</strong>
          <span
            v-if="ticket.requester_name && ticket.requester_email"
            class="ticket-header__field-hint"
          >&nbsp;{{ ticket.requester_email }}</span>
        </dd>
      </div>
      <div
        v-if="ticket.assignee_name"
        class="ticket-header__field"
      >
        <dt>{{ t('helpdesk.assignee') }}</dt>
        <dd><strong>{{ ticket.assignee_name }}</strong></dd>
      </div>
      <div class="ticket-header__field">
        <dt>{{ t('helpdesk.created') }}</dt>
        <dd>{{ formatDate(ticket.created_at) }}</dd>
      </div>
      <div class="ticket-header__field">
        <dt>{{ t('helpdesk.lastActivity') }}</dt>
        <dd>{{ formatDate(ticket.last_activity_at) }}</dd>
      </div>
    </dl>
  </n-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NCard, NTag } from 'naive-ui'
import TicketStatusBadge from './TicketStatusBadge.vue'
import type { HelpdeskTicketDetail } from '../../api/helpdesk'

defineProps<{ ticket: HelpdeskTicketDetail }>()
const { t, locale } = useI18n()

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(locale.value === 'ru' ? 'ru-RU' : 'en-US', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.ticket-header {
  /* nothing special — relies on default n-card padding */
}
.ticket-header__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.ticket-header__idline {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ticket-header__num {
  font-weight: 700;
  font-size: 14px;
  color: var(--color-text-secondary);
}
.ticket-header__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.ticket-header__subject {
  font-size: 19px;
  font-weight: 600;
  margin: 0 0 14px;
  line-height: 1.3;
}
.ticket-header__meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px 24px;
  margin: 0;
}
.ticket-header__field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.ticket-header__field dt {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
  font-weight: 600;
}
.ticket-header__field dd {
  margin: 0;
  font-size: 13px;
  color: var(--color-text);
  word-break: break-word;
}
.ticket-header__field-hint {
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 400;
}
</style>
