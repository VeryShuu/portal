<template>
  <n-card
    class="ticket-info"
    size="small"
    :bordered="true"
  >
    <template #header>
      <span class="ticket-info__title">{{ t('helpdesk.info.title') }}</span>
    </template>

    <dl class="ticket-info__fields">
      <div class="ticket-info__row">
        <dt class="ticket-info__label">
          {{ t('helpdesk.columnState') }}
        </dt>
        <dd class="ticket-info__value ticket-info__value--badge">
          <TicketStatusBadge :status="ticket.status" />
        </dd>
      </div>
      <div class="ticket-info__row">
        <dt class="ticket-info__label">
          {{ t('helpdesk.source') }}
        </dt>
        <dd class="ticket-info__value">
          {{ t(`helpdesk.sources.${ticket.source}`) }}
        </dd>
      </div>
      <div class="ticket-info__row">
        <dt class="ticket-info__label">
          {{ t('helpdesk.assignee') }}
        </dt>
        <dd class="ticket-info__value">
          {{ ticket.assignee_name ?? t('helpdesk.unassigned') }}
        </dd>
      </div>
      <div class="ticket-info__row">
        <dt class="ticket-info__label">
          {{ t('helpdesk.created') }}
        </dt>
        <dd class="ticket-info__value">
          {{ formatDate(ticket.created_at) }}
        </dd>
      </div>
      <div class="ticket-info__row">
        <dt class="ticket-info__label">
          {{ t('helpdesk.lastActivity') }}
        </dt>
        <dd class="ticket-info__value">
          {{ formatDate(ticket.last_activity_at) }}
        </dd>
      </div>
    </dl>
  </n-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NCard } from 'naive-ui'
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
/* Карточка служебных полей тикета в правом сайдбаре (над профилем заявителя). */
.ticket-info__title {
  font-size: 13px;
  font-weight: 600;
}
.ticket-info__fields {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ticket-info__row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.ticket-info__label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
  font-weight: 600;
  margin: 0;
}
.ticket-info__value {
  margin: 0;
  font-size: 13px;
  color: var(--color-text);
  word-break: break-word;
}
.ticket-info__value--badge {
  line-height: 1.8;
}
</style>
