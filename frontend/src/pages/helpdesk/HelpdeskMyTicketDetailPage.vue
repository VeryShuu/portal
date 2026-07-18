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
        {{ t('helpdesk.backToList') }}
      </n-button>
    </header>

    <n-spin :show="loading">
      <template v-if="ticket">
        <TicketDetailHeader :ticket="ticket" />

        <div class="ticket-layout">
          <div class="ticket-layout__main">
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
                :ticket-id="ticketId"
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
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { NSpin, NCard, NButton, NIcon, NAlert, useMessage } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import TicketDetailHeader from '../../components/helpdesk/TicketDetailHeader.vue'
import TicketInfoCard from '../../components/helpdesk/TicketInfoCard.vue'
import TicketMessageList from '../../components/helpdesk/TicketMessageList.vue'
import TicketReplyForm from '../../components/helpdesk/TicketReplyForm.vue'
import RequesterProfileCard from '../../components/helpdesk/RequesterProfileCard.vue'
import { fetchMyTicket, replyMyTicket, markMyTicketRead, type HelpdeskTicketDetail } from '../../api/helpdesk'
import { parseApiError } from '../../utils/parseApiError'
import { ROUTES } from '../../router'

const { t } = useI18n()
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
    // Best-efford: отметить тикет прочитанным для заявителя (снять подсветку
    // ответов агентов в «Мои заявки» — direction='outbound' в reads.py).
    // Не блокирует UI и не валит карточку при ошибке (read-state — косметика).
    // Зеркало агентского markTicketRead в HelpdeskAgentTicketDetailPage.
    void markMyTicketRead(ticketId).catch(() => {
      /* silent: read-state не критичен для просмотра переписки */
    })
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    loading.value = false
  }
}

async function onReply(payload: {
  body_html: string
  visibility: 'public' | 'internal'
  files: File[]
}) {
  replying.value = true
  try {
    await replyMyTicket(ticketId, { body_html: payload.body_html }, payload.files)
    message.success(t('helpdesk.replySent'))
    await load()
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    replying.value = false
  }
}

function goBack() {
  router.push(ROUTES.HELPDESK_MY)
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
.ticket-detail__closed {
  margin-top: 0;
}
</style>
