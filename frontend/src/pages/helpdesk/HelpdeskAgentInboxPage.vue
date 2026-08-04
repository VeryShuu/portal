<template>
  <div class="u-page-wrap u-page-wrap--standard">
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
    <n-spin :show="searchLoading">
      <template v-if="isSearchMode">
        <h2 class="inbox-section__title">
          {{ t('helpdesk.searchResults') }}
        </h2>
        <n-empty
          v-if="!searchLoading && searchItems.length === 0"
          :description="t('helpdesk.noTickets')"
          style="margin: 48px 0"
        />
        <TicketList
          v-else
          :items="searchItems"
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
            v-if="newTotal > LIMIT"
            class="helpdesk-pagination"
          >
            <n-pagination
              :page="newPage"
              :page-size="LIMIT"
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
            v-if="inWorkTotal > LIMIT"
            class="helpdesk-pagination"
          >
            <n-pagination
              :page="inWorkPage"
              :page-size="LIMIT"
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
import { parseApiError } from '../../utils/parseApiError'
import { useAgentInboxQuery } from '../../queries/helpdesk'
import { takeTicket } from '../../api/helpdesk'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../queries/keys'
import type { HelpdeskInboxParams } from '../../api/helpdesk'

const { t } = useI18n()
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()
const qc = useQueryClient()

const LIMIT = 20

// ── Search (плоский режим, FTS по всем) ──────────────────────────────────────
const q = ref('')
const searchPage = ref(1)
const isSearchMode = computed(() => q.value.trim().length > 0)

// ── Блок «Новые заявки» (неназначенные + status=new) ─────────────────────────
const newPage = ref(1)

// ── Блок «В работе» (мои / все назначенные, активные) ────────────────────────
const inWorkPage = ref(1)
const assignmentScope = ref<'mine' | 'all'>(
  localStorage.getItem('helpdesk.inbox.scope') === 'all' ? 'all' : 'mine',
)

const takingId = ref<string | null>(null)
const myId = computed(() => auth.user?.id)

// Архив вынесен на отдельную страницу /helpdesk/archive (роут helpdesk-archive).
const archiveHref = '/helpdesk/archive'

// ── Server state через TanStack Query (раньше — ручные ref + load*) ──────────
// useAgentInboxQuery реактивен к MaybeRefOrGetter<params>: смена page/scope/q
// пересоздаёт params → queryKey меняется → авто-refetch. enabled отключает
// запрос, пока условие не выполнено (search-only / inWork-mine ждёт myId).
const newParams = computed<HelpdeskInboxParams>(() => ({
  status: 'new',
  unassigned: true,
  limit: LIMIT,
  offset: (newPage.value - 1) * LIMIT,
}))
const newQ = useAgentInboxQuery(newParams, { enabled: () => !isSearchMode.value })
const newItems = computed(() => newQ.data.value?.items ?? [])
const newTotal = computed(() => newQ.data.value?.total ?? 0)
const newLoading = computed(() => newQ.isLoading.value)

const inWorkParams = computed<HelpdeskInboxParams>(() => {
  const isMine = assignmentScope.value === 'mine'
  return {
    activeOnly: true, // активные (new/open/pending); closed — в архиве
    // «Только мои» → assignee=me. «Все назначенные» → assigned=true
    // (assignee IS NOT NULL, иначе вернулись бы и неназначенные, которые
    // уже в верхнем блоке «Новые заявки»).
    assignee: isMine ? myId.value : undefined,
    assigned: !isMine || undefined,
    limit: LIMIT,
    offset: (inWorkPage.value - 1) * LIMIT,
  }
})
// Защита: в режиме «Только мои» нужен assignee=myId. Если user ещё не загружен
// (bootstrap async), запрос не активен — иначе бэкенд вернёт все активные тикеты
// (включая неназначенные). Когда myId появится → enabled станет true → авто-fetch.
const inWorkQ = useAgentInboxQuery(inWorkParams, { enabled: () => !isSearchMode.value && (assignmentScope.value === 'all' || !!myId.value) })
const inWorkItems = computed(() => inWorkQ.data.value?.items ?? [])
const inWorkTotal = computed(() => inWorkQ.data.value?.total ?? 0)
const inWorkLoading = computed(() => inWorkQ.isLoading.value)

const searchParams = computed<HelpdeskInboxParams>(() => ({
  q: q.value.trim(),
  limit: LIMIT,
  offset: (searchPage.value - 1) * LIMIT,
}))
const searchQ = useAgentInboxQuery(searchParams, { enabled: () => isSearchMode.value })
const searchItems = computed(() => searchQ.data.value?.items ?? [])
const searchTotal = computed(() => searchQ.data.value?.total ?? 0)
const searchLoading = computed(() => searchQ.isLoading.value)
const searchLimit = LIMIT

// Query-ошибки не всплывают в toast автоматически (main.ts::QueryCache.onError
// только console.error). Сохраняем прежний UX: показываем message.error при
// провале любого из трёх запросов. Дедупликация — разовый toast на каждый error.
watch(() => newQ.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })
watch(() => inWorkQ.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })
watch(() => searchQ.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })

// ── Handlers ─────────────────────────────────────────────────────────────────
// Реактивность: page/scope/q меняют computed params → queryKey → авто-refetch.
// Handlers только сбрасывают производный state (page) — ручной refetch не нужен.

function onSearchChange() {
  searchPage.value = 1
}

function onScopeChange() {
  localStorage.setItem('helpdesk.inbox.scope', assignmentScope.value)
  inWorkPage.value = 1
}

function changeNewPage(p: number) {
  newPage.value = p
}

function changeInWorkPage(p: number) {
  inWorkPage.value = p
}

function changeSearchPage(p: number) {
  searchPage.value = p
}

function goToTicket(id: string) {
  router.push({ name: 'helpdesk-ticket', params: { id } })
}

// onTake: прямой вызов takeTicket + invalidate inbox/agentTicketCounts (зеркало
// useTakeTicketMutation, но без per-id hook — здесь id динамический).
async function onTake(id: string) {
  takingId.value = id
  try {
    await takeTicket(id)
    message.success(t('helpdesk.taken'))
    // Взятый тикет уходит из «Новых» (статус ≠ new / появился assignee) →
    // возвращаем блок «Новые» на 1-ю страницу, иначе можно остаться на пустой.
    newPage.value = 1
    await qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicket(id) })
    await qc.invalidateQueries({ queryKey: queryKeys.helpdesk.inbox() })
    await qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicketCounts() })
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    takingId.value = null
  }
}
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
