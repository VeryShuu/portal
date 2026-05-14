<template>
  <div>
    <div class="tab-toolbar">
      <n-select
        v-model:value="statusFilter"
        :options="statusOptions"
        size="small"
        clearable
        :placeholder="t('feedback.statusLabel')"
        style="width:180px"
        @update:value="reload"
      />
      <n-select
        v-model:value="categoryFilter"
        :options="categoryOptions"
        size="small"
        clearable
        :placeholder="t('feedback.categoryLabel')"
        style="width:200px"
        @update:value="reload"
      />
      <n-input
        v-model:value="search"
        :placeholder="t('common.search')"
        clearable
        size="small"
        style="max-width:260px"
        @update:value="onSearch"
      />
    </div>

    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :pagination="paginationProps"
      :remote="true"
      :row-key="(row: FeedbackAdminOut) => row.id"
      striped
      class="data-table"
      :row-props="rowProps"
      @update:page="changePage"
    />

    <n-modal
      v-model:show="modalOpen"
      preset="card"
      :title="t('feedback.adminTab')"
      style="width:720px;max-width:96vw"
    >
      <div v-if="selected" class="detail">
        <div class="detail__head">
          <n-tag :type="categoryTagType(selected.category)" size="small">
            {{ t(`feedback.categories.${selected.category}`) }}
          </n-tag>
          <span class="muted">{{ formatDate(selected.created_at, locale) }}</span>
        </div>
        <div class="detail__author">
          <strong>{{ selected.author_name || t('feedback.deletedUser') }}</strong>
          <span v-if="selected.author_email" class="muted"> ({{ selected.author_email }})</span>
        </div>
        <div class="detail__message">{{ selected.message }}</div>
        <div v-if="selected.page_url" class="detail__url">
          <strong>{{ t('feedback.pageUrl') }}:</strong> {{ selected.page_url }}
        </div>

        <FeedbackAttachmentList
          v-if="selected.attachments.length"
          :attachments="selected.attachments"
          class="detail__atts"
        />

        <div class="detail__status">
          <span class="muted">{{ t('feedback.changeStatus') }}:</span>
          <n-select
            v-model:value="selected.status"
            :options="statusOptionsAll"
            size="small"
            style="width:200px"
            @update:value="onStatusChange"
          />
        </div>

        <div class="detail__replies">
          <h4>{{ t('feedback.repliesSection') }}</h4>
          <div v-if="!selected.replies.length" class="muted">
            {{ t('feedback.noRepliesYet') }}
          </div>
          <div v-else>
            <div v-for="r in selected.replies" :key="r.id" class="reply">
              <div class="reply__head">
                <strong>{{ r.admin_name || t('feedback.deletedAdmin') }}</strong>
                <span class="muted">{{ formatDate(r.created_at, locale) }}</span>
              </div>
              <div class="reply__msg">{{ r.message }}</div>
            </div>
          </div>
        </div>

        <div class="detail__reply-form">
          <n-input
            v-model:value="replyMessage"
            type="textarea"
            :rows="3"
            :placeholder="t('feedback.replyPlaceholder')"
            :maxlength="5000"
          />
          <div style="margin-top:8px;display:flex;gap:8px;justify-content:flex-end">
            <n-button :disabled="replying" @click="modalOpen = false">
              {{ t('common.close') }}
            </n-button>
            <n-button
              type="primary"
              :loading="replying"
              :disabled="!replyMessage.trim()"
              @click="submitReply"
            >
              {{ t('feedback.replyButton') }}
            </n-button>
          </div>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NDataTable,
  NInput,
  NModal,
  NSelect,
  NTag,
  useMessage,
  type DataTableColumns,
} from 'naive-ui'
import {
  getAllFeedback,
  getFeedbackById,
  replyToFeedback,
  updateFeedbackStatus,
  type FeedbackAdminOut,
  type FeedbackStatus,
} from '../../../api/feedback'
import FeedbackAttachmentList from '../../../components/FeedbackAttachmentList.vue'
import { formatDate } from '../../../utils/formatDate'
import { parseApiError } from '../../../utils/parseApiError'

const { t, locale } = useI18n()
const message = useMessage()

const items = ref<FeedbackAdminOut[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)

const statusFilter = ref<string | null>(null)
const categoryFilter = ref<string | null>(null)
const search = ref<string>('')
let searchTimer: ReturnType<typeof setTimeout> | null = null

const modalOpen = ref(false)
const selected = ref<FeedbackAdminOut | null>(null)
const replyMessage = ref('')
const replying = ref(false)

const statusOptions = computed(() => [
  { label: t('feedback.statuses.open'), value: 'open' },
  { label: t('feedback.statuses.in_progress'), value: 'in_progress' },
  { label: t('feedback.statuses.closed'), value: 'closed' },
])
const statusOptionsAll = statusOptions
const categoryOptions = computed(() => [
  { label: t('feedback.categories.bug'), value: 'bug' },
  { label: t('feedback.categories.suggestion'), value: 'suggestion' },
  { label: t('feedback.categories.other'), value: 'other' },
])

function categoryTagType(c: string): 'error' | 'info' | 'default' {
  if (c === 'bug') return 'error'
  if (c === 'suggestion') return 'info'
  return 'default'
}
function statusTagType(s: string): 'warning' | 'info' | 'success' | 'default' {
  if (s === 'open') return 'warning'
  if (s === 'in_progress') return 'info'
  if (s === 'closed') return 'success'
  return 'default'
}

const columns = computed<DataTableColumns<FeedbackAdminOut>>(() => [
  {
    title: t('feedback.dateColumn'),
    key: 'created_at',
    width: 130,
    render: row => formatDate(row.created_at, locale.value),
  },
  {
    title: t('feedback.categoryLabel'),
    key: 'category',
    width: 140,
    render: row => h(NTag, { type: categoryTagType(row.category), size: 'small' }, {
      default: () => t(`feedback.categories.${row.category}`),
    }),
  },
  {
    title: t('feedback.authorColumn'),
    key: 'author',
    render: row => row.author_name || t('feedback.deletedUser'),
  },
  {
    title: t('feedback.statusLabel'),
    key: 'status',
    width: 130,
    render: row => h(NTag, { type: statusTagType(row.status), size: 'small' }, {
      default: () => t(`feedback.statuses.${row.status}`),
    }),
  },
  {
    title: t('feedback.messageLabel'),
    key: 'message',
    render: row => row.message.length > 100 ? row.message.slice(0, 100) + '…' : row.message,
  },
])

const paginationProps = computed(() => ({
  page: page.value,
  pageSize,
  itemCount: total.value,
  showSizePicker: false,
}))

function rowProps(row: FeedbackAdminOut) {
  return {
    style: 'cursor: pointer;',
    onClick: () => openDetail(row.id),
  }
}

async function load() {
  loading.value = true
  try {
    const res = await getAllFeedback({
      status: statusFilter.value || undefined,
      category: categoryFilter.value || undefined,
      q: search.value.trim() || undefined,
      limit: pageSize,
      offset: (page.value - 1) * pageSize,
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

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    reload()
  }, 350)
}

async function changePage(p: number) {
  page.value = p
  await load()
}

async function openDetail(id: string) {
  try {
    selected.value = await getFeedbackById(id)
    replyMessage.value = ''
    modalOpen.value = true
  } catch (err) {
    message.error(parseApiError(err, t))
  }
}

async function onStatusChange(val: FeedbackStatus) {
  if (!selected.value) return
  try {
    const updated = await updateFeedbackStatus(selected.value.id, val)
    selected.value = updated
    const idx = items.value.findIndex(i => i.id === updated.id)
    if (idx >= 0) items.value[idx] = updated
  } catch (err) {
    message.error(parseApiError(err, t))
  }
}

async function submitReply() {
  if (!selected.value || !replyMessage.value.trim()) return
  replying.value = true
  const id = selected.value.id
  try {
    await replyToFeedback(id, { message: replyMessage.value.trim() })
    replyMessage.value = ''
    selected.value = await getFeedbackById(id)
    await load()
  } catch (err) {
    message.error(parseApiError(err, t))
  } finally {
    replying.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.tab-toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
  align-items: center;
}
.detail__head {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.detail__author {
  margin-bottom: 12px;
}
.detail__message {
  white-space: pre-wrap;
  background: var(--color-bg-elevated, #f7f7f8);
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 12px;
}
.detail__url {
  font-size: 12px;
  word-break: break-all;
  margin-bottom: 12px;
}
.detail__status {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.detail__replies h4 {
  margin: 8px 0;
  font-size: 14px;
}
.reply {
  padding: 8px 10px;
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
.detail__reply-form {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--divider-color, #eee);
}
.muted {
  color: var(--color-text-secondary, #888);
  font-size: 13px;
}
</style>
