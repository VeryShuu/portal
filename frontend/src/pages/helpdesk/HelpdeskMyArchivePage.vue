<template>
  <div class="u-page-wrap u-page-wrap--narrow">
    <header class="page-head">
      <h1 class="u-page-head__title">
        {{ t('helpdesk.myArchiveTitle') }}
      </h1>
      <n-button
        quaternary
        tag="a"
        href="/helpdesk/my"
      >
        {{ t('helpdesk.backToList') }}
      </n-button>
    </header>

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
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NSpin, NEmpty, NPagination, NButton, useMessage } from 'naive-ui'
import TicketListItem from '../../components/helpdesk/TicketListItem.vue'
import { fetchMyTickets, type HelpdeskTicketListItem } from '../../api/helpdesk'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const router = useRouter()
const message = useMessage()

// Архив заявителя = только его закрытые тикеты. Бэкенд ``GET /tickets/my``
// уже умеет ``status=closed`` (миграции не нужны). Без переключателя mine/all
// (все тикеты свои — делить не по чему, в отличие от агентского архива).
const items = ref<HelpdeskTicketListItem[]>([])
const total = ref(0)
const page = ref(1)
const limit = 20
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await fetchMyTickets({
      status: 'closed',
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
