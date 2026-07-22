<template>
  <n-card
    v-if="participants.length > 0"
    class="ticket-participants"
    size="small"
    :bordered="true"
  >
    <template #header>
      <span class="ticket-participants__title">{{ t('helpdesk.participants.title') }}</span>
    </template>
    <ul class="ticket-participants__list">
      <li
        v-for="p in participants"
        :key="p.email"
        class="ticket-participants__item"
        :class="{ 'ticket-participants__item--requester': p.is_requester }"
      >
        <span class="ticket-participants__name">{{ nameOrEmail(p) }}</span>
        <span
          v-if="p.name"
          class="ticket-participants__email"
        >{{ p.email }}</span>
        <span
          v-if="p.is_requester"
          class="ticket-participants__badge"
        >{{ t('helpdesk.participants.requester') }}</span>
      </li>
    </ul>
  </n-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NCard } from 'naive-ui'
import type { HelpdeskParticipant } from '../../api/helpdesk'

defineProps<{
  /** Участники тикета «в сборе» (requester + Cc + авторы сообщений). Берётся
   *  из ``ticket.participants`` (агентский view, миграция 083). */
  participants: HelpdeskParticipant[]
}>()

const { t } = useI18n()

function nameOrEmail(p: HelpdeskParticipant): string {
  return p.name ?? p.email
}
</script>

<style scoped>
/* Блок «Участники» в правом сайдбаре карточки тикета (под профилем заявителя).
   Показывает всех адресатов переписки — источник для «Ответить всем». */
.ticket-participants__title {
  font-size: 13px;
  font-weight: 600;
}
.ticket-participants__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ticket-participants__item {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
  font-size: 13px;
  min-width: 0;
}
.ticket-participants__name {
  font-weight: 500;
  color: var(--color-text);
  word-break: break-word;
}
.ticket-participants__email {
  color: var(--color-text-muted);
  font-size: 12px;
  word-break: break-all;
}
.ticket-participants__badge {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 700;
  color: var(--color-brand, #18a058);
  background: rgba(24, 160, 88, 0.1);
  padding: 1px 6px;
  border-radius: 8px;
}
.ticket-participants__item--requester .ticket-participants__name {
  font-weight: 600;
}
</style>
