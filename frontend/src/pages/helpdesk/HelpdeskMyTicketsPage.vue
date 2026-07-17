<template>
  <div class="u-page-wrap u-page-wrap--narrow">
    <header class="page-head">
      <h1 class="u-page-head__title">
        {{ t('helpdesk.myTitle') }}
      </h1>
      <n-button
        type="primary"
        @click="showCreate = true"
      >
        <template #icon>
          <n-icon><component :is="AddOutline" /></n-icon>
        </template>
        {{ t('helpdesk.createButton') }}
      </n-button>
    </header>

    <div class="helpdesk-filters">
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
        <n-radio-button value="closed">
          {{ t('helpdesk.statuses.closed') }}
        </n-radio-button>
      </n-radio-group>
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
        <div class="ticket-table__head">
          <span>{{ t('helpdesk.columnNumber') }}</span>
          <span>{{ t('helpdesk.columnState') }}</span>
          <span>{{ t('helpdesk.columnSubject') }}</span>
          <span>{{ t('helpdesk.columnAssignee') }}</span>
          <span>{{ t('helpdesk.columnUpdated') }}</span>
        </div>
        <div class="ticket-table__body">
          <TicketListItem
            v-for="ticket in items"
            :key="ticket.id"
            :ticket="ticket"
            @open="goToTicket"
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

    <TicketCreateModal
      v-model:show="showCreate"
      @created="reload"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NSpin, NEmpty, NPagination, NButton, NIcon, NRadioGroup, NRadioButton, useMessage } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import TicketListItem from '../../components/helpdesk/TicketListItem.vue'
import TicketCreateModal from '../../components/helpdesk/TicketCreateModal.vue'
import { fetchMyTickets, type HelpdeskTicketListItem, type HelpdeskStatus } from '../../api/helpdesk'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const router = useRouter()
const message = useMessage()

const items = ref<HelpdeskTicketListItem[]>([])
const total = ref(0)
const page = ref(1)
const limit = 20
const statusFilter = ref('')
const loading = ref(false)
const showCreate = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await fetchMyTickets({
      status: (statusFilter.value || undefined) as HelpdeskStatus | undefined,
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
  router.push({ name: 'helpdesk-my-ticket', params: { id } })
}

load()
</script>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.helpdesk-filters {
  margin-bottom: 16px;
}
.ticket-table {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-surface);
}
.ticket-table__head {
  display: grid;
  grid-template-columns: 56px 92px minmax(0, 1fr) 150px 104px;
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
.ticket-table__head span:last-child {
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
