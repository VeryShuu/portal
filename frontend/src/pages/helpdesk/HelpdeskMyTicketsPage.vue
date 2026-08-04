<template>
  <div class="u-page-wrap u-page-wrap--wide">
    <header class="page-head">
      <h1 class="u-page-head__title">
        {{ t('helpdesk.myTitle') }}
      </h1>
      <div class="page-head__actions">
        <n-button
          quaternary
          tag="a"
          href="/helpdesk/my/archive"
        >
          {{ t('helpdesk.archive') }}
        </n-button>
        <n-button
          type="primary"
          @click="showCreate = true"
        >
          <template #icon>
            <n-icon><component :is="AddOutline" /></n-icon>
          </template>
          {{ t('helpdesk.createButton') }}
        </n-button>
      </div>
    </header>

    <!-- Блок «Ожидают принятия» — неназначенные (без агента) -->
    <section class="inbox-section">
      <header class="inbox-section__head">
        <h2 class="inbox-section__title">
          {{ t('helpdesk.sectionWaiting') }}
          <span
            v-if="waitingTotal"
            class="inbox-section__count"
          >{{ waitingTotal }}</span>
        </h2>
      </header>
      <n-spin :show="waitingLoading">
        <n-empty
          v-if="!waitingLoading && waitingItems.length === 0"
          :description="t('helpdesk.noTickets')"
          style="margin: 24px 0"
        />
        <TicketList
          v-else
          :items="waitingItems"
          mode="user"
          :sort-column="sortColumn"
          :sort-order="sortOrder"
          @open="goToTicket"
          @sort="onSortToggle"
        />
      </n-spin>
      <div
        v-if="waitingTotal > waitingLimit"
        class="helpdesk-pagination"
      >
        <n-pagination
          :page="waitingPage"
          :page-size="waitingLimit"
          :item-count="waitingTotal"
          @update:page="changeWaitingPage"
        />
      </div>
    </section>

    <!-- Блок «В работе у специалиста» — назначенные (с агентом) -->
    <section class="inbox-section">
      <header class="inbox-section__head">
        <h2 class="inbox-section__title">
          {{ t('helpdesk.sectionMyInWork') }}
          <span
            v-if="inWorkTotal"
            class="inbox-section__count"
          >{{ inWorkTotal }}</span>
        </h2>
      </header>
      <n-spin :show="inWorkLoading">
        <n-empty
          v-if="!inWorkLoading && inWorkItems.length === 0"
          :description="t('helpdesk.noTickets')"
          style="margin: 24px 0"
        />
        <TicketList
          v-else
          :items="inWorkItems"
          mode="user"
          :sort-column="sortColumn"
          :sort-order="sortOrder"
          @open="goToTicket"
          @sort="onSortToggle"
        />
      </n-spin>
      <div
        v-if="inWorkTotal > inWorkLimit"
        class="helpdesk-pagination"
      >
        <n-pagination
          :page="inWorkPage"
          :page-size="inWorkLimit"
          :item-count="inWorkTotal"
          @update:page="changeInWorkPage"
        />
      </div>
    </section>

    <TicketCreateModal
      v-model:show="showCreate"
      @created="loadAll"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NSpin, NEmpty, NPagination, NButton, NIcon, useMessage } from 'naive-ui'
import { AddOutline } from '@vicons/ionicons5'
import TicketList from '../../components/helpdesk/TicketList.vue'
import TicketCreateModal from '../../components/helpdesk/TicketCreateModal.vue'
import { fetchMyTickets, type HelpdeskTicketListItem } from '../../api/helpdesk'
import { useHelpdeskTicketSort } from '../../composables/useHelpdeskTicketSort'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const router = useRouter()
const message = useMessage()

// Двухблочный вид по образцу HelpdeskAgentInboxPage. Деление по assignee
// (не по status): пользователь видит «ожидают принятия» (без агента) и
// «в работе у специалиста» (с назначенным). Отвечает на вопрос «когда мной
// займутся» лучше, чем деление по статусу тикета.
const waitingItems = ref<HelpdeskTicketListItem[]>([])
const waitingTotal = ref(0)
const waitingPage = ref(1)
const waitingLimit = 20
const waitingLoading = ref(false)

const inWorkItems = ref<HelpdeskTicketListItem[]>([])
const inWorkTotal = ref(0)
const inWorkPage = ref(1)
const inWorkLimit = 20
const inWorkLoading = ref(false)

const showCreate = ref(false)

// Серверная сортировка своих заявок (общая для обоих блоков).
const { sortColumn, sortOrder, apiParams: sortApiParams, toggle: toggleSort } = useHelpdeskTicketSort()

function onSortToggle(id: Parameters<typeof toggleSort>[0]): void {
  toggleSort(id)
  waitingPage.value = 1
  inWorkPage.value = 1
  loadAll()
}

async function loadWaiting() {
  waitingLoading.value = true
  try {
    const res = await fetchMyTickets({
      unassigned: true,
      activeOnly: true,
      ...sortApiParams.value,
      limit: waitingLimit,
      offset: (waitingPage.value - 1) * waitingLimit,
    })
    waitingItems.value = res.items
    waitingTotal.value = res.total
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    waitingLoading.value = false
  }
}

async function loadInWork() {
  inWorkLoading.value = true
  try {
    const res = await fetchMyTickets({
      assigned: true,
      activeOnly: true,
      ...sortApiParams.value,
      limit: inWorkLimit,
      offset: (inWorkPage.value - 1) * inWorkLimit,
    })
    inWorkItems.value = res.items
    inWorkTotal.value = res.total
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    inWorkLoading.value = false
  }
}

async function loadAll() {
  await Promise.all([loadWaiting(), loadInWork()])
}

function changeWaitingPage(p: number) {
  waitingPage.value = p
  loadWaiting()
}

function changeInWorkPage(p: number) {
  inWorkPage.value = p
  loadInWork()
}

function goToTicket(id: string) {
  router.push({ name: 'helpdesk-my-ticket', params: { id } })
}

loadAll()
</script>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-head__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.inbox-section {
  margin-bottom: 32px;
}
.inbox-section__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.inbox-section__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  display: flex;
  align-items: center;
  gap: 8px;
}
.inbox-section__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  padding: 0 6px;
  font-size: 11px;
  font-weight: 600;
  line-height: 16px;
  color: var(--color-text-muted);
  background: rgba(0, 0, 0, 0.06);
  border-radius: 999px;
}
[data-theme='dark'] .inbox-section__count {
  background: rgba(255, 255, 255, 0.1);
}
.helpdesk-pagination {
  margin-top: 16px;
  display: flex;
  justify-content: center;
}
</style>
