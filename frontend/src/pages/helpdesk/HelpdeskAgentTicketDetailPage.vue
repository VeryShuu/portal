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
              v-if="!ticket.archived && !ticket.assignee_user_id"
              size="small"
              type="primary"
              ghost
              :loading="acting"
              @click="onTake"
            >
              {{ t('helpdesk.take') }}
            </n-button>

            <n-select
              v-else-if="!ticket.archived"
              v-model:value="selectedStatus"
              :options="statusOptions"
              size="small"
              style="width: 180px"
              :loading="acting"
              :disabled="assignedToOther"
              :title="assignedToOther ? t('helpdesk.statusLocked') : undefined"
              @update:value="onStatusChange"
            />

            <n-button
              v-if="!ticket.archived && ticket.status === 'closed'"
              size="small"
              :loading="acting"
              :disabled="assignedToOther"
              @click="onReopen"
            >
              {{ t('helpdesk.reopen') }}
            </n-button>

            <!-- Полное удаление заявки — только администратор. Необратимая
                 операция (hard-delete: БД + файлы), поэтому под confirm-диалогом.
                 Доступна из карточки живого тикета; после удаления — возврат в
                 инбокс (карточка больше недоступна). -->
            <n-popconfirm
              v-if="auth.isAdmin && !ticket.archived"
              :positive-text="t('helpdesk.delete')"
              :negative-text="t('common.cancel')"
              @positive-click="onDelete"
            >
              <template #trigger>
                <n-button
                  size="small"
                  type="error"
                  ghost
                  :loading="acting"
                >
                  <template #icon>
                    <n-icon><component :is="TrashOutline" /></n-icon>
                  </template>
                  {{ t('helpdesk.delete') }}
                </n-button>
              </template>
              {{ t('helpdesk.deleteConfirm', { number: ticket.number }) }}
            </n-popconfirm>
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

            <n-card
              v-if="!ticket.archived && !assignedToOther"
              class="ticket-detail__reply"
            >
              <div class="ticket-detail__reply-title">
                {{ t('helpdesk.agentReply') }}
              </div>
              <TicketReplyForm
                agent-mode
                :ticket-id="ticketId"
                :loading="replying"
                :participants="ticket.participants"
                @submit="onReply"
              />
            </n-card>
            <n-alert
              v-else-if="ticket.archived"
              class="ticket-detail__locked"
              type="default"
              :show-icon="false"
            >
              {{ t('helpdesk.closedNoReply') }}
            </n-alert>
            <n-alert
              v-else
              class="ticket-detail__locked"
              type="info"
              :show-icon="true"
            >
              <div class="ticket-detail__locked-title">
                {{ t('helpdesk.lockedByOther', { name: ticket.assignee_name ?? '—' }) }}
              </div>
              {{ t('helpdesk.lockedByOtherHint') }}
            </n-alert>
          </div>

          <aside class="ticket-layout__aside">
            <TicketInfoCard
              :ticket="ticket"
              :editable="!ticket.archived"
            />
            <RequesterProfileCard :profile="ticket.requester_profile" />
            <TicketParticipantsCard :participants="ticket.participants ?? []" />
          </aside>
        </div>
      </template>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { NSpin, NCard, NButton, NIcon, NSelect, NPopconfirm, NAlert, useMessage } from 'naive-ui'
import { useQueryClient } from '@tanstack/vue-query'
import { ArrowBackOutline, TrashOutline } from '@vicons/ionicons5'
import TicketDetailHeader from '../../components/helpdesk/TicketDetailHeader.vue'
import TicketInfoCard from '../../components/helpdesk/TicketInfoCard.vue'
import TicketMessageList from '../../components/helpdesk/TicketMessageList.vue'
import TicketReplyForm from '../../components/helpdesk/TicketReplyForm.vue'
import RequesterProfileCard from '../../components/helpdesk/RequesterProfileCard.vue'
import TicketParticipantsCard from '../../components/helpdesk/TicketParticipantsCard.vue'
import {
  fetchAgentTicket,
  takeTicket,
  changeTicketStatus,
  reopenTicket,
  deleteTicket,
  replyAgentTicket,
  markTicketRead,
  type HelpdeskTicketDetail,
  type HelpdeskStatus,
} from '../../api/helpdesk'
import { parseApiError, getErrorStatus } from '../../utils/parseApiError'
import { useAuthStore } from '../../stores/auth'
import { queryKeys } from '../../queries/keys'
import { ROUTES } from '../../router'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()
const qc = useQueryClient()

const ticketId = String(route.params.id)
const ticket = ref<HelpdeskTicketDetail | null>(null)
const loading = ref(false)
const acting = ref(false)
const replying = ref(false)
const selectedStatus = ref<HelpdeskStatus | null>(null)
let assignmentPoll: ReturnType<typeof setInterval> | undefined

const statusOptions = computed(() =>
  [
    { value: 'open', label: t('helpdesk.statuses.open') },
    { value: 'pending', label: t('helpdesk.statuses.pending') },
    { value: 'closed', label: t('helpdesk.statuses.closed') },
  ],
)

// Блокировка за назначенным агентом (assignee-lock): заявка закреплена за
// другим агентом → не он не может отвечать/менять статус/reopen. Админ
// подчиняется тому же правилу (без bypass — решение продукта). Сменить
// ответственного на себя можно всегда (через ``TicketInfoCard`` справа).
const assignedToOther = computed(
  () =>
    !!ticket.value?.assignee_user_id &&
    ticket.value.assignee_user_id !== auth.user?.id,
)

watch(ticket, (t) => {
  if (t) selectedStatus.value = t.status
})

async function load() {
  loading.value = true
  try {
    ticket.value = await fetchAgentTicket(ticketId)
    selectedStatus.value = ticket.value.status
    // Best-efford: отметить тикет прочитанным для агента (снять подсветку в
    // инбоксе — миграция 080). Не блокирует UI и не валит карточку при ошибке
    // (read-state — косметика, как notifications.read). Повторное открытие
    // карточки = UPSERT, идемпотентно. После успеха инвалидируем счётчик
    // меню — красный бейдж гаснет сразу, не дожидаясь поллинга (60 c).
    void markTicketRead(ticketId)
      .then(() => qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicketCounts() }))
      .catch(() => {
        /* silent: read-state не критичен для просмотра переписки */
      })
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    loading.value = false
  }
}

/**
 * A second agent can have the same unassigned card open. Poll only while it
 * remains unassigned, so the passive view promptly becomes read-only without
 * adding background traffic for tickets that already have an owner.
 */
async function refreshUnassignedTicket() {
  if (ticket.value?.assignee_user_id) return
  try {
    const updated = await fetchAgentTicket(ticketId)
    const wasUnassigned = ticket.value?.assignee_user_id === null
    ticket.value = updated
    selectedStatus.value = updated.status
    if (wasUnassigned && updated.assignee_user_id && updated.assignee_user_id !== auth.user?.id) {
      message.info(t('helpdesk.takenByOtherToast', { name: updated.assignee_name ?? '—' }))
    }
  } catch {
    // Polling is a convenience; the next interval or a user action retries.
  }
}

onMounted(() => {
  assignmentPoll = setInterval(() => {
    void refreshUnassignedTicket()
  }, 15_000)
})

onBeforeUnmount(() => {
  if (assignmentPoll) clearInterval(assignmentPoll)
})

async function withActing(fn: () => Promise<void>) {
  acting.value = true
  try {
    await fn()
    await load()
  } catch (e) {
    if (!(await handleAssigneeLock(e))) {
      message.error(parseApiError(e, t))
    }
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

/** Специфичный toast на 403 assignee-lock: стандартный «Недостаточно прав»
 * не объясняет причину, а assignee мог смениться (другая вкладка) — перезагружаем
 * карточку, чтобы UI пришёл в актуальное состояние. Safety-net поверх disabled-
 * состояния в шаблоне (гонка load↔assign). */
async function handleAssigneeLock(e: unknown): Promise<boolean> {
  const status = getErrorStatus(e)
  if (status === 409) {
    await load()
    message.error(t('helpdesk.takenByOtherToast', { name: ticket.value?.assignee_name ?? '—' }))
    return true
  }
  if (status === 403) {
    message.error(t('helpdesk.lockedToast'))
    await load()
    return true
  }
  return false
}

async function onDelete() {
  // Hard-delete админом — необратимо. После успешного удаления тикета нельзя
  // вызывать load() (404 — строки больше нет), поэтому своя функция вместо
  // withActing: acting-флаг на время запроса, затем toast + переход в инбокс.
  acting.value = true
  try {
    await deleteTicket(ticketId)
    message.success(t('helpdesk.deleted'))
    router.push(ROUTES.HELPDESK_INBOX)
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    acting.value = false
  }
}

async function onReply(payload: {
  body_html: string
  files: File[]
  cc?: string[]
}) {
  replying.value = true
  try {
    await replyAgentTicket(
      ticketId,
      { body_html: payload.body_html, cc: payload.cc },
      payload.files,
    )
    message.success(t('helpdesk.replySent'))
    await load()
  } catch (e) {
    if (!(await handleAssigneeLock(e))) {
      message.error(parseApiError(e, t))
    }
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
.ticket-detail__locked {
  margin: 0 0 16px;
}
.ticket-detail__locked-title {
  font-weight: 600;
  margin-bottom: 4px;
}
</style>
