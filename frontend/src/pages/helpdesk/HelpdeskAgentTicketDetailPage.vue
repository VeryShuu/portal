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
        {{ t('helpdesk.backToInbox') }}
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
            <span>
              {{ t('helpdesk.requester') }}:
              <strong>{{ ticket.requester_name ?? ticket.requester_email }}</strong>
              <span class="ticket-detail__email">({{ ticket.requester_email }})</span>
            </span>
            <span v-if="ticket.assignee_name">
              {{ t('helpdesk.assignee') }}: <strong>{{ ticket.assignee_name }}</strong>
            </span>
          </div>

          <!-- Agent actions -->
          <div class="ticket-actions">
            <n-button
              v-if="!ticket.assignee_user_id"
              size="small"
              type="primary"
              ghost
              :loading="acting"
              @click="onTake"
            >
              {{ t('helpdesk.take') }}
            </n-button>

            <n-select
              v-else
              v-model:value="selectedStatus"
              :options="statusOptions"
              size="small"
              style="width: 200px"
              :loading="acting"
              @update:value="onStatusChange"
            />

            <n-button
              v-if="ticket.status === 'closed'"
              size="small"
              :loading="acting"
              @click="onReopen"
            >
              {{ t('helpdesk.reopen') }}
            </n-button>
          </div>
        </n-card>

        <div class="ticket-detail__messages">
          <TicketMessageList
            :messages="ticket.messages"
            agent-mode
          />
        </div>

        <n-card class="ticket-detail__reply">
          <div class="ticket-detail__reply-title">
            {{ t('helpdesk.agentReply') }}
          </div>
          <TicketReplyForm
            agent-mode
            :loading="replying"
            @submit="onReply"
          />
        </n-card>
      </template>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { NSpin, NCard, NButton, NIcon, NSelect, useMessage } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import TicketStatusBadge from '../../components/helpdesk/TicketStatusBadge.vue'
import TicketMessageList from '../../components/helpdesk/TicketMessageList.vue'
import TicketReplyForm from '../../components/helpdesk/TicketReplyForm.vue'
import {
  fetchAgentTicket,
  takeTicket,
  changeTicketStatus,
  reopenTicket,
  replyAgentTicket,
  type HelpdeskTicketDetail,
  type HelpdeskStatus,
} from '../../api/helpdesk'
import { parseApiError } from '../../utils/parseApiError'
import { ROUTES } from '../../router'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const message = useMessage()

const ticketId = String(route.params.id)
const ticket = ref<HelpdeskTicketDetail | null>(null)
const loading = ref(false)
const acting = ref(false)
const replying = ref(false)
const selectedStatus = ref<HelpdeskStatus | null>(null)

const statusOptions = computed(() =>
  [
    { value: 'open', label: t('helpdesk.statuses.open') },
    { value: 'pending', label: t('helpdesk.statuses.pending') },
    { value: 'resolved', label: t('helpdesk.statuses.resolved') },
    { value: 'closed', label: t('helpdesk.statuses.closed') },
  ],
)

watch(ticket, (t) => {
  if (t) selectedStatus.value = t.status
})

async function load() {
  loading.value = true
  try {
    ticket.value = await fetchAgentTicket(ticketId)
    selectedStatus.value = ticket.value.status
  } catch (e) {
    message.error(parseApiError(e, () => t('errors.generic')))
  } finally {
    loading.value = false
  }
}

async function withActing(fn: () => Promise<void>) {
  acting.value = true
  try {
    await fn()
    await load()
  } catch (e) {
    message.error(parseApiError(e, () => t('errors.generic')))
  } finally {
    acting.value = false
  }
}

function onTake() {
  withActing(async () => {
    await takeTicket(ticketId)
    message.success(t('helpdesk.taken'))
  })
}

function onStatusChange(value: 'open' | 'pending' | 'resolved' | 'closed') {
  withActing(async () => {
    await changeTicketStatus(ticketId, value)
    message.success(t('helpdesk.statusChanged'))
  })
}

function onReopen() {
  withActing(async () => {
    await reopenTicket(ticketId)
    message.success(t('helpdesk.reopened'))
  })
}

async function onReply(payload: { body: string; visibility: 'public' | 'internal'; files: File[] }) {
  replying.value = true
  try {
    await replyAgentTicket(
      ticketId,
      { body_text: payload.body, visibility: payload.visibility },
      payload.files,
    )
    message.success(t('helpdesk.replySent'))
    await load()
  } catch (e) {
    message.error(parseApiError(e, () => t('errors.generic')))
  } finally {
    replying.value = false
  }
}

function goBack() {
  router.push(ROUTES.HELPDESK_INBOX)
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
.ticket-detail__email {
  margin-left: 6px;
  opacity: 0.8;
}
.ticket-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: 16px;
}
.ticket-detail__messages {
  margin: 16px 0;
}
.ticket-detail__reply-title {
  font-weight: 600;
  margin-bottom: 10px;
}
</style>
