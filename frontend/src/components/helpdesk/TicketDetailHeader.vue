<template>
  <n-card class="ticket-header">
    <div class="ticket-header__row">
      <span class="ticket-header__num">#{{ ticket.number }}</span>
      <h1 class="ticket-header__subject">{{ ticket.subject }}</h1>
      <div class="ticket-header__actions">
        <slot name="actions" />
      </div>
    </div>
  </n-card>
</template>

<script setup lang="ts">
import { NCard } from 'naive-ui'
import type { HelpdeskTicketDetail } from '../../api/helpdesk'

defineProps<{ ticket: HelpdeskTicketDetail }>()
</script>

<style scoped>
.ticket-header__row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}
.ticket-header__num {
  font-weight: 700;
  font-size: 14px;
  color: var(--color-text-secondary);
  flex: 0 0 auto;
}
.ticket-header__subject {
  font-size: 19px;
  font-weight: 600;
  margin: 0;
  line-height: 1.3;
  flex: 1 1 auto;
  min-width: 0;
  word-break: break-word;
}
.ticket-header__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  flex: 0 0 auto;
  margin-left: auto;
}
</style>
