<template>
  <div class="u-page-wrap u-page-wrap--wide">
    <header class="page-head page-head--row">
      <h1 class="u-page-head__title">
        {{ t('helpdesk.sectionArchive') }}
      </h1>
      <n-button
        quaternary
        tag="a"
        :href="inboxHref"
      >
        {{ t('helpdesk.backToInbox') }}
      </n-button>
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
        v-model:value="assignmentScope"
        size="small"
        @update:value="reload"
      >
        <n-radio-button value="mine">
          {{ t('helpdesk.filterMine') }}
        </n-radio-button>
        <n-radio-button value="all">
          {{ t('helpdesk.filterAllAssigned') }}
        </n-radio-button>
      </n-radio-group>
    </div>

    <n-spin :show="loading">
      <n-empty
        v-if="!loading && items.length === 0"
        :description="t('helpdesk.noTickets')"
        style="margin: 48px 0"
      />
      <TicketList
        v-else
        :items="items"
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
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NSpin, NEmpty, NPagination, NInput, NRadioGroup, NRadioButton, NButton, useMessage } from 'naive-ui'
import TicketList from '../../components/helpdesk/TicketList.vue'
import { useAuthStore } from '../../stores/auth'
import { fetchAgentTickets, type HelpdeskTicketListItem } from '../../api/helpdesk'
import { useHelpdeskTicketSort } from '../../composables/useHelpdeskTicketSort'
import { parseApiError } from '../../utils/parseApiError'
import { ROUTES } from '../../router'

const { t } = useI18n()
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

// Инбокс вынесен на отдельную страницу /helpdesk (роут helpdesk). Ссылка
// рендерится как нативная ``<a>`` (``tag="a"`` + ``:href``) — тот же стиль, что
// у кнопки «Архив» в инбоксе агента (HelpdeskAgentInboxPage.vue) и кнопки
// «К моим заявкам» в архиве заявителя (HelpdeskMyArchivePage.vue): единый язык
// навигации между списками helpdesk.
const inboxHref = ROUTES.HELPDESK_INBOX

const items = ref<HelpdeskTicketListItem[]>([])
const total = ref(0)
const page = ref(1)
const limit = 20
const q = ref('')
const assignmentScope = ref<'mine' | 'all'>(
  localStorage.getItem('helpdesk.inbox.scope') === 'all' ? 'all' : 'mine',
)
const loading = ref(false)
const myId = computed(() => auth.user?.id)

// Серверная сортировка архива (закрытые тикеты).
const { sortColumn, sortOrder, apiParams: sortApiParams, toggle: toggleSort } = useHelpdeskTicketSort()

function onSortToggle(id: Parameters<typeof toggleSort>[0]): void {
  toggleSort(id)
  page.value = 1
  load()
}

async function load() {
  // В режиме «Только мои» нужен assignee=myId; если user ещё не загружен —
  // ждём (перезагрузка сработает через watch(myId)).
  const isMine = assignmentScope.value === 'mine'
  if (isMine && !myId.value) return
  loading.value = true
  try {
    // Архив = только closed (resolved упразднён, миграция 079). Один запрос,
    // без мержа.
    const scopeParams = isMine ? { assignee: myId.value } : { assigned: true }
    const res = await fetchAgentTickets({
      status: 'closed',
      ...scopeParams,
      q: q.value.trim() || undefined,
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

// user может быть ещё не загружен при первичном mount (bootstrap async).
watch(myId, (newId, oldId) => {
  if (newId && !oldId) load()
})

load()
</script>

<style scoped>
.page-head {
  margin-bottom: 16px;
}
.page-head--row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.helpdesk-filters {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.helpdesk-pagination {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}
</style>
