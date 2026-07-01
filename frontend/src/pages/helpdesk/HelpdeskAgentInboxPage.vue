<template>
  <div class="u-page-wrap u-page-wrap--wide">
    <header class="page-head">
      <h1 class="u-page-head__title">
        {{ t('helpdesk.inboxTitle') }}
      </h1>
    </header>

    <div class="helpdesk-filters">
      <n-input
        v-model:value="q"
        :placeholder="t('helpdesk.searchPlaceholder')"
        clearable
        style="max-width: 280px"
        @update:value="reload"
      />
      <n-radio-group
        v-model:value="statusFilter"
        size="small"
        @update:value="reload"
      >
        <n-radio-button value="">
          {{ t('helpdesk.statuses.all') }}
        </n-radio-button>
        <n-radio-button value="new">
          {{ t('helpdesk.statuses.new') }}
        </n-radio-button>
        <n-radio-button value="open">
          {{ t('helpdesk.statuses.open') }}
        </n-radio-button>
        <n-radio-button value="pending">
          {{ t('helpdesk.statuses.pending') }}
        </n-radio-button>
        <n-radio-button value="resolved">
          {{ t('helpdesk.statuses.resolved') }}
        </n-radio-button>
        <n-radio-button value="closed">
          {{ t('helpdesk.statuses.closed') }}
        </n-radio-button>
      </n-radio-group>
      <n-checkbox
        v-model:checked="unassignedOnly"
        @update:checked="reload"
      >
        {{ t('helpdesk.unassignedOnly') }}
      </n-checkbox>
    </div>

    <n-spin :show="loading">
      <n-empty
        v-if="!loading && items.length === 0"
        :description="t('helpdesk.noTickets')"
        style="margin: 48px 0"
      />
      <div class="ticket-cards">
        <n-card
          v-for="ticket in items"
          :key="ticket.id"
          class="ticket-card"
          hoverable
          @click="goToTicket(ticket.id)"
        >
          <div class="ticket-card__head">
            <span class="ticket-card__num">#{{ ticket.number }}</span>
            <TicketStatusBadge :status="ticket.status" />
            <n-tag
              v-if="ticket.source === 'email'"
              size="tiny"
              :bordered="false"
            >
              email
            </n-tag>
            <n-tag
              v-else
              size="tiny"
              :bordered="false"
            >
              web
            </n-tag>
            <span class="ticket-card__date">{{ formatDate(ticket.last_activity_at) }}</span>
          </div>
          <div class="ticket-card__subject">
            {{ ticket.subject }}
          </div>
          <div class="ticket-card__meta">
            <span class="ticket-card__requester">
              {{ ticket.requester_name ?? ticket.requester_email }}
            </span>
            <span
              v-if="ticket.assignee_name"
              class="ticket-card__assignee"
            >
              {{ t('helpdesk.assignee') }}: {{ ticket.assignee_name }}
            </span>
            <n-button
              v-else
              size="tiny"
              type="primary"
              ghost
              :loading="takingId === ticket.id"
              @click.stop="onTake(ticket.id)"
            >
              {{ t('helpdesk.take') }}
            </n-button>
          </div>
        </n-card>
      </div>
    </n-spin>

    <div
      v-if="total > limit"
      class="helpdesk-pagination"
    >
      <n-pagination
        :page="page"
        :page-size="limit"
        :item-count="total"
        @update:page="changePage"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NSpin, NEmpty, NCard, NPagination, NInput, NRadioGroup, NRadioButton, NCheckbox, NTag, NButton, useMessage } from 'naive-ui'
import TicketStatusBadge from '../../components/helpdesk/TicketStatusBadge.vue'
import { fetchAgentTickets, takeTicket, type HelpdeskTicketListItem, type HelpdeskStatus } from '../../api/helpdesk'
import { parseApiError } from '../../utils/parseApiError'

const { t, locale } = useI18n()
const router = useRouter()
const message = useMessage()

const items = ref<HelpdeskTicketListItem[]>([])
const total = ref(0)
const page = ref(1)
const limit = 20
const q = ref('')
const statusFilter = ref('')
const unassignedOnly = ref(false)
const loading = ref(false)
const takingId = ref<string | null>(null)

async function load() {
  loading.value = true
  try {
    const res = await fetchAgentTickets({
      status: (statusFilter.value || undefined) as HelpdeskStatus | undefined,
      unassigned: unassignedOnly.value || undefined,
      q: q.value.trim() || undefined,
      limit,
      offset: (page.value - 1) * limit,
    })
    items.value = res.items
    total.value = res.total
  } catch (e) {
    message.error(parseApiError(e, () => t('errors.generic')))
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  load()
}
function changePage(p: number) {
  page.value = p
  load()
}
function goToTicket(id: string) {
  router.push({ name: 'helpdesk-ticket', params: { id } })
}

async function onTake(id: string) {
  takingId.value = id
  try {
    await takeTicket(id)
    message.success(t('helpdesk.taken'))
    await load()
  } catch (e) {
    message.error(parseApiError(e, () => t('errors.generic')))
  } finally {
    takingId.value = null
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(locale.value === 'ru' ? 'ru-RU' : 'en-US', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

load()
</script>

<style scoped>
.page-head {
  margin-bottom: 16px;
}
.helpdesk-filters {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.ticket-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ticket-card {
  cursor: pointer;
}
.ticket-card__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.ticket-card__num {
  font-weight: 600;
  color: var(--color-text-secondary);
}
.ticket-card__date {
  margin-left: auto;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.ticket-card__subject {
  font-weight: 500;
  margin-bottom: 6px;
}
.ticket-card__meta {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 13px;
  color: var(--color-text-secondary);
}
.helpdesk-pagination {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}
</style>
