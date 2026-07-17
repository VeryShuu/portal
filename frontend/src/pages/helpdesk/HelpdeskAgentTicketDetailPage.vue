<template>
  <div class="u-page-wrap">
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
        <TicketDetailHeader :ticket="ticket">
          <template #actions>
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
              style="width: 180px"
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
          </template>
        </TicketDetailHeader>

        <div class="ticket-layout">
          <div class="ticket-layout__main">
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
                :ticket-id="ticketId"
                :loading="replying"
                @submit="onReply"
              />
            </n-card>
          </div>

          <aside class="ticket-layout__aside">
            <TicketInfoCard :ticket="ticket" />
            <RequesterProfileCard :profile="ticket.requester_profile" />
          </aside>
        </div>
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
import TicketDetailHeader from '../../components/helpdesk/TicketDetailHeader.vue'
import TicketInfoCard from '../../components/helpdesk/TicketInfoCard.vue'
import TicketMessageList from '../../components/helpdesk/TicketMessageList.vue'
import TicketReplyForm from '../../components/helpdesk/TicketReplyForm.vue'
import RequesterProfileCard from '../../components/helpdesk/RequesterProfileCard.vue'
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
    message.error(parseApiError(e, t))
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
    message.error(parseApiError(e, t))
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

function onStatusChange(value: 'open' | 'pending' | 'closed') {
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

async function onReply(payload: {
  body_html: string
  visibility: 'public' | 'internal'
  files: File[]
}) {
  replying.value = true
  try {
    await replyAgentTicket(
      ticketId,
      { body_html: payload.body_html, visibility: payload.visibility },
      payload.files,
    )
    message.success(t('helpdesk.replySent'))
    await load()
  } catch (e) {
    message.error(parseApiError(e, t))
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
/* Двухколоночный layout: переписка слева, профиль заявителя справа.
   На узких экранах сворачивается в одну колонку (OTRS-образный сайдбар). */
.ticket-layout {
  display: flex;
  gap: 20px;
  align-items: flex-start;
  margin-top: 16px;
}
.ticket-layout__main {
  flex: 1;
  min-width: 0;
}
.ticket-layout__aside {
  flex: 0 0 280px;
  position: sticky;
  top: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
@media (max-width: 900px) {
  .ticket-layout {
    flex-direction: column;
  }
  .ticket-layout__aside {
    position: static;
    flex-basis: auto;
    width: 100%;
  }
}
.ticket-detail__messages {
  margin: 0 0 16px;
}
.ticket-detail__reply-title {
  font-weight: 600;
  margin-bottom: 10px;
}
</style>
