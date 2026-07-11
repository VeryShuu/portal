<template>
  <div class="u-page-wrap u-page-wrap--narrow">
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
      <div
        v-else
        class="ticket-table"
      >
        <div class="ticket-table__head ticket-table__head--agent">
          <span>{{ t('helpdesk.columnNumber') }}</span>
          <span>{{ t('helpdesk.columnState') }}</span>
          <span>{{ t('helpdesk.columnSubject') }}</span>
          <span>{{ t('helpdesk.columnRequester') }}</span>
          <span>{{ t('helpdesk.columnOwner') }}</span>
          <span>{{ t('helpdesk.columnUpdated') }}</span>
        </div>
        <div class="ticket-table__body">
          <TicketListItem
            v-for="ticket in items"
            :key="ticket.id"
            :ticket="ticket"
            agent-mode
            :taking="takingId === ticket.id"
            @open="goToTicket"
            @take="onTake"
          />
        </div>
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
import { NSpin, NEmpty, NPagination, NInput, NRadioGroup, NRadioButton, NCheckbox, useMessage } from 'naive-ui'
import TicketListItem from '../../components/helpdesk/TicketListItem.vue'
import { fetchAgentTickets, takeTicket, type HelpdeskTicketListItem, type HelpdeskStatus } from '../../api/helpdesk'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
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
    message.error(parseApiError(e, t))
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
    message.error(parseApiError(e, t))
  } finally {
    takingId.value = null
  }
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
.ticket-table {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-surface);
}
.ticket-table__head {
  display: grid;
  grid-template-columns: 56px 92px minmax(0, 1fr) 150px 150px 104px;
  gap: 12px;
  padding: 8px 14px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-muted);
  background: var(--color-bg-muted);
  border-bottom: 1px solid var(--color-border);
}
.ticket-table__head--agent span:last-child {
  text-align: right;
}
.ticket-table__body :deep(.ticket-row:last-child) {
  border-bottom: none;
}
.helpdesk-pagination {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}
</style>
