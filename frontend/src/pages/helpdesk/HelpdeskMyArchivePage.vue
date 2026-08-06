<template>
  <div class="u-page-wrap u-page-wrap--standard">
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
      <TicketList
        v-else
        :items="items"
        mode="user"
        :sort-column="sortColumn"
        :sort-order="sortOrder"
        @open="goToTicket"
        @sort="onSortToggle"
      />
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
import TicketList from '../../components/helpdesk/TicketList.vue'
import { fetchMyTickets, type HelpdeskTicketListItem } from '../../api/helpdesk'
import { useHelpdeskTicketSort } from '../../composables/useHelpdeskTicketSort'
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

// Серверная сортировка архива заявителя.
const { sortColumn, sortOrder, apiParams: sortApiParams, toggle: toggleSort } = useHelpdeskTicketSort()

function onSortToggle(id: Parameters<typeof toggleSort>[0]): void {
  toggleSort(id)
  page.value = 1
  load()
}

async function load() {
  loading.value = true
  try {
    const res = await fetchMyTickets({
      status: 'closed',
      ...sortApiParams.value,
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
.helpdesk-pagination {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}
</style>
