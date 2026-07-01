<template>
  <div class="u-page-wrap u-page-wrap--narrow">
    <header class="page-head">
      <n-button
        text
        @click="goBack"
      >
        <template #icon>
          <n-icon><component :is="ArrowBackOutline" /></n-icon>
        </template>
        {{ t('helpdesk.backToList') }}
      </n-button>
    </header>

    <n-spin :show="loading">
      <template v-if="ticket">
        <n-card>
          <div class="ticket-detail__head">
            <div>
              <div class="ticket-detail__num">
                #{{ ticket.number }}
              </div>
              <h1 class="ticket-detail__subject">
                {{ ticket.subject }}
              </h1>
            </div>
            <TicketStatusBadge :status="ticket.status" />
          </div>
          <div class="ticket-detail__meta">
            <span v-if="ticket.assignee_name">
              {{ t('helpdesk.assignee') }}: <strong>{{ ticket.assignee_name }}</strong>
            </span>
            <span class="ticket-detail__date">
              {{ t('helpdesk.created') }}: {{ formatDate(ticket.created_at) }}
            </span>
          </div>
        </n-card>

        <div class="ticket-detail__messages">
          <TicketMessageList :messages="ticket.messages" />
        </div>

        <n-card
          v-if="!isClosed"
          class="ticket-detail__reply"
        >
          <div class="ticket-detail__reply-title">
            {{ t('helpdesk.yourReply') }}
          </div>
          <TicketReplyForm
            :loading="replying"
            @submit="onReply"
          />
        </n-card>
        <n-alert
          v-else
          class="ticket-detail__closed"
          type="default"
          :show-icon="false"
        >
          {{ t('helpdesk.closedNoReply') }}
        </n-alert>
      </template>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { NSpin, NCard, NButton, NIcon, NAlert, useMessage } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import TicketStatusBadge from '../../components/helpdesk/TicketStatusBadge.vue'
import TicketMessageList from '../../components/helpdesk/TicketMessageList.vue'
import TicketReplyForm from '../../components/helpdesk/TicketReplyForm.vue'
import { fetchMyTicket, replyMyTicket, type HelpdeskTicketDetail } from '../../api/helpdesk'
import { parseApiError } from '../../utils/parseApiError'
import { ROUTES } from '../../router'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const message = useMessage()

const ticketId = String(route.params.id)
const ticket = ref<HelpdeskTicketDetail | null>(null)
const loading = ref(false)
const replying = ref(false)

const isClosed = computed(() => ticket.value?.status === 'closed')

async function load() {
  loading.value = true
  try {
    ticket.value = await fetchMyTicket(ticketId)
  } catch (e) {
    message.error(parseApiError(e, () => t('errors.generic')))
  } finally {
    loading.value = false
  }
}

async function onReply(payload: { body: string; visibility: 'public' | 'internal'; files: File[] }) {
  replying.value = true
  try {
    await replyMyTicket(ticketId, { body_text: payload.body }, payload.files)
    message.success(t('helpdesk.replySent'))
    await load()
  } catch (e) {
    message.error(parseApiError(e, () => t('errors.generic')))
  } finally {
    replying.value = false
  }
}

function goBack() {
  router.push(ROUTES.HELPDESK_MY)
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value === 'ru' ? 'ru-RU' : 'en-US', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

load()
</script>

<style scoped>
.page-head {
  margin-bottom: 12px;
}
.ticket-detail__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}
.ticket-detail__num {
  font-size: 13px;
  color: var(--color-text-secondary);
}
.ticket-detail__subject {
  font-size: 20px;
  font-weight: 600;
  margin: 4px 0 0;
}
.ticket-detail__meta {
  display: flex;
  gap: 24px;
  margin-top: 12px;
  font-size: 13px;
  color: var(--color-text-secondary);
}
.ticket-detail__messages {
  margin: 16px 0;
}
.ticket-detail__reply-title {
  font-weight: 600;
  margin-bottom: 10px;
}
.ticket-detail__closed {
  margin-top: 16px;
}
</style>
