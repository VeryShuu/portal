<template>
  <div class="my-fb">
    <header class="page-head">
      <h1 class="u-page-head__title">
        {{ t('feedback.myTicketsTitle') }}
      </h1>
    </header>

    <div class="filter-bar">
      <n-radio-group
        v-model:value="statusFilter"
        size="small"
        @update:value="reload"
      >
        <n-radio-button value="">
          {{ t('feedback.filterAll') }}
        </n-radio-button>
        <n-radio-button value="open">
          {{ t('feedback.statuses.open') }}
        </n-radio-button>
        <n-radio-button value="in_progress">
          {{ t('feedback.statuses.in_progress') }}
        </n-radio-button>
        <n-radio-button value="closed">
          {{ t('feedback.statuses.closed') }}
        </n-radio-button>
      </n-radio-group>
    </div>

    <div
      v-if="loading"
      class="loader"
    >
      <n-spin />
    </div>

    <EmptyState
      v-else-if="!items.length"
      :title="t('feedback.noTickets')"
    />

    <div
      v-else
      class="cards"
    >
      <n-card
        v-for="item in items"
        :key="item.id"
        :ref="el => setCardRef(item.id, el)"
        class="fb-card"
        :class="{ 'fb-card--open': expanded.has(item.id) }"
        hoverable
        @click="toggle(item.id)"
      >
        <div class="fb-card__head">
          <n-tag
            :type="categoryTagType(item.category)"
            size="small"
          >
            {{ t(`feedback.categories.${item.category}`) }}
          </n-tag>
          <n-tag
            :type="statusTagType(item.status)"
            size="small"
          >
            {{ t(`feedback.statuses.${item.status}`) }}
          </n-tag>
          <span class="fb-card__date">{{ formatDate(item.created_at, locale) }}</span>
          <span
            v-if="item.replies.length"
            class="fb-card__count"
          >
            {{ item.replies.length }} {{ t('feedback.repliesSection') }}
          </span>
        </div>

        <div
          v-if="!expanded.has(item.id)"
          class="fb-card__preview"
        >
          {{ truncate(item.message, 200) }}
        </div>

        <div
          v-else
          class="fb-card__details"
          @click.stop
        >
          <div class="fb-card__message">
            {{ item.message }}
          </div>
          <div
            v-if="item.page_url"
            class="fb-card__url"
          >
            <strong>{{ t('feedback.pageUrl') }}:</strong> {{ item.page_url }}
          </div>
          <FeedbackAttachmentList
            v-if="item.attachments.length"
            :attachments="item.attachments"
            class="fb-card__atts"
          />
          <div class="fb-card__replies">
            <h4>{{ t('feedback.repliesSection') }}</h4>
            <div
              v-if="!item.replies.length"
              class="muted"
            >
              {{ t('feedback.noRepliesYet') }}
            </div>
            <div v-else>
              <div
                v-for="r in item.replies"
                :key="r.id"
                class="reply"
              >
                <div class="reply__head">
                  <strong>{{ r.admin_name || t('feedback.deletedAdmin') }}</strong>
                  <span class="muted">{{ formatDate(r.created_at, locale) }}</span>
                </div>
                <div class="reply__msg">
                  {{ r.message }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </n-card>
    </div>

    <div
      v-if="total > limit"
      class="pager"
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
import { onMounted, ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  NCard,
  NPagination,
  NRadioButton,
  NRadioGroup,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import EmptyState from '../components/EmptyState.vue'
import FeedbackAttachmentList from '../components/FeedbackAttachmentList.vue'
import {
  getMyFeedback,
  getMyFeedbackById,
  type FeedbackOut,
} from '../api/feedback'
import { formatDate } from '../utils/formatDate'
import { parseApiError } from '../utils/parseApiError'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const message = useMessage()

const items = ref<FeedbackOut[]>([])
const total = ref(0)
const page = ref(1)
const limit = 20
const loading = ref(false)
const statusFilter = ref<string>('')
const expanded = ref<Set<string>>(new Set())
const cardRefs = new Map<string, HTMLElement>()

function setCardRef(id: string, el: unknown) {
  if (!el) { cardRefs.delete(id); return }
  const maybeVue = el as { $el?: HTMLElement }
  if (maybeVue.$el) cardRefs.set(id, maybeVue.$el)
  else if (el instanceof HTMLElement) cardRefs.set(id, el)
}

function categoryTagType(c: string) {
  if (c === 'bug') return 'error'
  if (c === 'suggestion') return 'info'
  return 'default'
}
function statusTagType(s: string) {
  if (s === 'open') return 'warning'
  if (s === 'in_progress') return 'info'
  if (s === 'closed') return 'success'
  return 'default'
}

function truncate(s: string, n: number) {
  if (s.length <= n) return s
  return s.slice(0, n) + '…'
}

function toggle(id: string) {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
  expanded.value = new Set(expanded.value)
}

async function load() {
  loading.value = true
  try {
    const res = await getMyFeedback({
      status: statusFilter.value || undefined,
      limit,
      offset: (page.value - 1) * limit,
    })
    items.value = res.items
    total.value = res.total
  } catch (err) {
    message.error(parseApiError(err, t))
  } finally {
    loading.value = false
  }
}

async function reload() {
  page.value = 1
  await load()
}

async function changePage(p: number) {
  page.value = p
  await load()
}

async function handleOpenQuery() {
  const openId = typeof route.query.open === 'string' ? route.query.open : null
  if (!openId) return

  let item = items.value.find(i => i.id === openId)
  if (!item) {
    try {
      item = await getMyFeedbackById(openId)
      if (!items.value.find(i => i.id === item!.id)) {
        items.value = [item, ...items.value]
      }
    } catch {
      message.error(t('feedback.notFound'))
      router.replace({ query: { ...route.query, open: undefined } })
      return
    }
  }
  expanded.value.add(openId)
  expanded.value = new Set(expanded.value)
  await nextTick()
  const el = cardRefs.get(openId)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

onMounted(async () => {
  await load()
  await handleOpenQuery()
})

watch(() => route.query.open, async () => {
  await handleOpenQuery()
})
</script>

<style scoped>
.my-fb {
  max-width: 960px;
  margin: 0 auto;
}
.page-head {
  margin-bottom: 20px;
}
.filter-bar {
  margin-bottom: 16px;
}
.cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.fb-card {
  cursor: pointer;
  transition: box-shadow 0.15s ease;
}
.fb-card__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.fb-card__date {
  color: var(--color-text-secondary, #888);
  font-size: 12px;
  margin-left: auto;
}
.fb-card__count {
  color: var(--color-text-secondary, #888);
  font-size: 12px;
}
.fb-card__preview {
  white-space: pre-wrap;
  color: var(--color-text);
}
.fb-card__details {
  cursor: default;
}
.fb-card__message {
  white-space: pre-wrap;
  margin-bottom: 12px;
}
.fb-card__url {
  font-size: 12px;
  color: var(--color-text-secondary, #888);
  margin-bottom: 12px;
  word-break: break-all;
}
.fb-card__replies h4 {
  margin: 12px 0 8px;
  font-size: 14px;
}
.reply {
  padding: 10px;
  background: var(--color-bg-elevated, #f7f7f8);
  border-radius: 6px;
  margin-bottom: 8px;
}
.reply__head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 13px;
}
.reply__msg {
  white-space: pre-wrap;
}
.muted {
  color: var(--color-text-secondary, #888);
  font-size: 13px;
}
.loader {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}
.pager {
  margin-top: 20px;
  display: flex;
  justify-content: center;
}
</style>
