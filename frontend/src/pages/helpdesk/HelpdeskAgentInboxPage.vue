<template>
  <div class="u-page-wrap u-page-wrap--narrow">
    <header class="page-head page-head--row">
      <h1 class="u-page-head__title">
        {{ t('helpdesk.inboxTitle') }}
      </h1>
      <n-button
        quaternary
        tag="a"
        :href="archiveHref"
      >
        {{ t('helpdesk.archive') }}
      </n-button>
    </header>

    <div class="helpdesk-filters">
      <n-input
        v-model:value="q"
        :placeholder="t('helpdesk.searchPlaceholder')"
        clearable
        style="max-width: 280px"
        @update:value="onSearchChange"
      />
    </div>

    <!-- Режим поиска: плоский список (FTS по всем тикетам) -->
    <n-spin :show="loading">
      <template v-if="isSearchMode">
        <h2 class="inbox-section__title">
          {{ t('helpdesk.searchResults') }}
        </h2>
        <n-empty
          v-if="!loading && items.length === 0"
          :description="t('helpdesk.noTickets')"
          style="margin: 48px 0"
        />
        <TicketList
          v-else
          :items="items"
          :taking-id="takingId"
          @open="goToTicket"
          @take="onTake"
        />
        <div
          v-if="searchTotal > searchLimit"
          class="helpdesk-pagination"
        >
          <n-pagination
            :page="searchPage"
            :page-size="searchLimit"
            :item-count="searchTotal"
            @update:page="changeSearchPage"
          />
        </div>
      </template>

      <!-- Обычный режим: два блока (новые / в работе) + архив toggle -->
      <template v-else>
        <!-- Блок 1: новые неназначенные заявки -->
        <section class="inbox-section">
          <header class="inbox-section__head">
            <h2 class="inbox-section__title">
              {{ t('helpdesk.sectionNew') }}
              <span
                v-if="newTotal"
                class="inbox-section__count"
              >{{ newTotal }}</span>
            </h2>
          </header>
          <n-empty
            v-if="!newLoading && newItems.length === 0"
            :description="t('helpdesk.noNewTickets')"
            style="margin: 24px 0"
          />
          <TicketList
            v-else
            :items="newItems"
            :taking-id="takingId"
            @open="goToTicket"
            @take="onTake"
          />
          <div
            v-if="newTotal > newLimit"
            class="helpdesk-pagination"
          >
            <n-pagination
              :page="newPage"
              :page-size="newLimit"
              :item-count="newTotal"
              @update:page="changeNewPage"
            />
          </div>
        </section>

        <!-- Блок 2: в работе (мои / все назначенные) -->
        <section class="inbox-section">
          <header class="inbox-section__head">
            <h2 class="inbox-section__title">
              {{ t('helpdesk.sectionInWork') }}
              <span
                v-if="inWorkTotal"
                class="inbox-section__count"
              >{{ inWorkTotal }}</span>
            </h2>
            <n-radio-group
              v-model:value="assignmentScope"
              size="small"
              @update:value="onScopeChange"
            >
              <n-radio-button value="mine">
                {{ t('helpdesk.filterMine') }}
              </n-radio-button>
              <n-radio-button value="all">
                {{ t('helpdesk.filterAllAssigned') }}
              </n-radio-button>
            </n-radio-group>
          </header>
          <n-empty
            v-if="!inWorkLoading && inWorkItems.length === 0"
            :description="t('helpdesk.noTickets')"
            style="margin: 24px 0"
          />
          <TicketList
            v-else
            :items="inWorkItems"
            :taking-id="takingId"
            @open="goToTicket"
            @take="onTake"
          />
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
      </template>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NSpin, NEmpty, NPagination, NInput, NRadioGroup, NRadioButton, NButton, useMessage } from 'naive-ui'
import TicketList from '../../components/helpdesk/TicketList.vue'
import { useAuthStore } from '../../stores/auth'
import {
  fetchAgentTickets,
  takeTicket,
  type HelpdeskTicketListItem,
} from '../../api/helpdesk'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

// ── Search (плоский режим, FTS по всем) ──────────────────────────────────────
const q = ref('')
const items = ref<HelpdeskTicketListItem[]>([])
const searchTotal = ref(0)
const searchPage = ref(1)
const searchLimit = 20
const loading = ref(false)

// ── Блок «Новые заявки» (неназначенные + status=new) ─────────────────────────
const newItems = ref<HelpdeskTicketListItem[]>([])
const newTotal = ref(0)
const newPage = ref(1)
const newLimit = 20
const newLoading = ref(false)

// ── Блок «В работе» (мои / все назначенные, активные) ────────────────────────
const inWorkItems = ref<HelpdeskTicketListItem[]>([])
const inWorkTotal = ref(0)
const inWorkPage = ref(1)
const inWorkLimit = 20
const inWorkLoading = ref(false)
const assignmentScope = ref<'mine' | 'all'>(
  localStorage.getItem('helpdesk.inbox.scope') === 'all' ? 'all' : 'mine',
)

const takingId = ref<string | null>(null)
const myId = computed(() => auth.user?.id)

const isSearchMode = computed(() => q.value.trim().length > 0)
// Архив вынесен на отдельную страницу /helpdesk/archive (роут helpdesk-archive).
const archiveHref = '/helpdesk/archive'

// ── Загрузка ─────────────────────────────────────────────────────────────────

async function loadNew() {
  newLoading.value = true
  try {
    const res = await fetchAgentTickets({
      status: 'new',
      unassigned: true,
      limit: newLimit,
      offset: (newPage.value - 1) * newLimit,
    })
    newItems.value = res.items
    newTotal.value = res.total
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    newLoading.value = false
  }
}

function changeNewPage(p: number) {
  newPage.value = p
  loadNew()
}

async function loadInWork() {
  // Защита: в режиме «Только мои» нужен assignee=myId. Если user ещё не
  // загружен (bootstrap async), не шлём запрос без assignee — иначе бэкенд
  // вернёт все активные тикеты (включая неназначенные). Перезагрузка
  // сработает через watch(myId) после загрузки user.
  const isMine = assignmentScope.value === 'mine'
  if (isMine && !myId.value) return
  inWorkLoading.value = true
  try {
    const res = await fetchAgentTickets({
      activeOnly: true, // активные (new/open/pending); closed — в архиве
      // «Только мои» → assignee=me. «Все назначенные» → assigned=true
      // (assignee IS NOT NULL, иначе вернулись бы и неназначенные, которые
      // уже в верхнем блоке «Новые заявки»).
      assignee: isMine ? myId.value : undefined,
      assigned: !isMine || undefined,
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

async function loadSearch() {
  if (!isSearchMode.value) return
  loading.value = true
  try {
    const res = await fetchAgentTickets({
      q: q.value.trim(),
      limit: searchLimit,
      offset: (searchPage.value - 1) * searchLimit,
    })
    items.value = res.items
    searchTotal.value = res.total
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    loading.value = false
  }
}

async function loadAll() {
  if (isSearchMode.value) {
    await loadSearch()
  } else {
    await Promise.all([loadNew(), loadInWork()])
  }
}

// user может быть ещё не загружен при первичном mount (bootstrap async).
// Когда myId появится — перезагружаем блок «В работе» (зависит от assignee).
watch(myId, (newId, oldId) => {
  if (newId && !oldId && !isSearchMode.value) {
    void loadInWork()
  }
})

// ── Handlers ─────────────────────────────────────────────────────────────────

function onSearchChange() {
  searchPage.value = 1
  if (isSearchMode.value) loadSearch()
  else loadAll()
}

function onScopeChange() {
  localStorage.setItem('helpdesk.inbox.scope', assignmentScope.value)
  inWorkPage.value = 1
  loadInWork()
}

function changeInWorkPage(p: number) {
  inWorkPage.value = p
  loadInWork()
}

function changeSearchPage(p: number) {
  searchPage.value = p
  loadSearch()
}

function goToTicket(id: string) {
  router.push({ name: 'helpdesk-ticket', params: { id } })
}

async function onTake(id: string) {
  takingId.value = id
  try {
    await takeTicket(id)
    message.success(t('helpdesk.taken'))
    // Взятый тикет уходит из «Новых» (статус ≠ new / появился assignee) →
    // возвращаем блок «Новые» на 1-ю страницу, иначе можно остаться на пустой.
    newPage.value = 1
    await loadAll()
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    takingId.value = null
  }
}

loadAll()
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
.inbox-section {
  margin-bottom: 32px;
}
.inbox-section__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.inbox-section__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.inbox-section__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 7px;
  border-radius: 11px;
  background: var(--color-bg-muted);
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 700;
}
.helpdesk-pagination {
  margin-top: 16px;
  display: flex;
  justify-content: center;
}
</style>
