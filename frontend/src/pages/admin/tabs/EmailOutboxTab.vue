<template>
  <div class="outbox-wrap">
    <div
      class="branding-section__hint"
      style="margin-bottom:12px"
    >
      {{ t('admin.emailOutbox.hint') }}
    </div>

    <div
      v-if="counts"
      class="outbox-stats"
    >
      <n-tag
        v-for="(label, key) in STATUS_LABELS"
        :key="key"
        :type="STATUS_TYPE[key]"
        size="small"
        class="outbox-stat"
      >
        {{ t(label) }}: {{ counts[key] ?? 0 }}
      </n-tag>
      <span
        v-if="dlqCount > 0"
        class="outbox-dlq-alert"
      >
        {{ t('admin.emailOutbox.dlqAlert', { n: dlqCount }) }}
      </span>
    </div>

    <div class="outbox-filters">
      <n-select
        v-model:value="filters.status"
        :options="statusOptions"
        :placeholder="t('admin.emailOutbox.filters.statusPlaceholder')"
        clearable
        size="small"
        style="min-width:160px"
      />
      <n-select
        v-model:value="filters.kind"
        :options="kindOptions"
        :placeholder="t('admin.emailOutbox.filters.kindPlaceholder')"
        clearable
        size="small"
        style="min-width:160px"
      />
      <n-input
        v-model:value="filters.to_email"
        :placeholder="t('admin.emailOutbox.filters.toEmailPlaceholder')"
        clearable
        size="small"
        :maxlength="320"
        style="min-width:200px"
      />
      <n-input
        v-model:value="filters.q"
        :placeholder="t('admin.emailOutbox.filters.search')"
        clearable
        size="small"
        :maxlength="200"
        style="min-width:240px;flex:1"
      />
      <n-button
        size="small"
        type="primary"
        @click="reload"
      >
        {{ t('admin.emailOutbox.filters.apply') }}
      </n-button>
      <n-button
        size="small"
        @click="resetFilters"
      >
        {{ t('admin.emailOutbox.filters.reset') }}
      </n-button>
      <n-button
        size="small"
        @click="reload"
      >
        <template #icon>
          <n-icon><RefreshOutline /></n-icon>
        </template>
        {{ t('common.refresh') }}
      </n-button>
    </div>

    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :pagination="pagination"
      :remote="true"
      :row-key="(row: EmailOutboxItem) => row.id"
      size="small"
      striped
      class="data-table"
      @update:page="onPageChange"
    />

    <n-modal
      v-model:show="detailOpen"
      preset="card"
      :title="t('admin.emailOutbox.detailTitle')"
      style="width:760px;max-width:96vw"
      :mask-closable="true"
    >
      <div
        v-if="detail"
        class="outbox-detail"
      >
        <div class="outbox-detail__row">
          <strong>{{ t('admin.emailOutbox.cols.status') }}:</strong>
          <n-tag
            :type="STATUS_TYPE[detail.status]"
            size="small"
          >
            {{ t(STATUS_LABELS[detail.status]) }}
          </n-tag>
        </div>
        <div class="outbox-detail__row">
          <strong>{{ t('admin.emailOutbox.cols.kind') }}:</strong>
          {{ detail.kind }}
        </div>
        <div class="outbox-detail__row">
          <strong>{{ t('admin.emailOutbox.cols.to') }}:</strong>
          {{ detail.to_email }}
        </div>
        <div class="outbox-detail__row">
          <strong>{{ t('admin.emailOutbox.cols.subject') }}:</strong>
          {{ detail.subject }}
        </div>
        <div class="outbox-detail__row">
          <strong>{{ t('admin.emailOutbox.cols.attempts') }}:</strong>
          {{ detail.attempts }} / {{ detail.max_attempts }}
        </div>
        <div
          v-if="detail.next_attempt_at"
          class="outbox-detail__row"
        >
          <strong>{{ t('admin.emailOutbox.cols.nextAttempt') }}:</strong>
          {{ formatDate(detail.next_attempt_at) }}
        </div>
        <div
          v-if="detail.last_error"
          class="outbox-detail__row outbox-detail__error"
        >
          <strong>{{ t('admin.emailOutbox.lastError') }}
            ({{ detail.last_error_type }} / {{ detail.last_error_class }}):</strong>
          <pre class="outbox-detail__pre">{{ detail.last_error }}</pre>
        </div>
        <details class="outbox-detail__body">
          <summary>{{ t('admin.emailOutbox.showBody') }}</summary>
          <pre class="outbox-detail__pre">{{ detail.body_html }}</pre>
        </details>
      </div>
      <template #footer>
        <div class="modal-footer">
          <n-button
            v-if="detail && canRetry(detail.status)"
            type="primary"
            :loading="acting"
            @click="onRetry(detail.id)"
          >
            {{ t('admin.emailOutbox.actions.retry') }}
          </n-button>
          <n-button
            v-if="detail && canCancel(detail.status)"
            :loading="acting"
            @click="onCancel(detail.id)"
          >
            {{ t('admin.emailOutbox.actions.cancel') }}
          </n-button>
          <n-button @click="detailOpen = false">
            {{ t('common.close') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, h, reactive, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NDataTable,
  NIcon,
  NInput,
  NModal,
  NSelect,
  NTag,
  useMessage,
} from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'
import {
  type EmailOutboxFilters,
  type EmailOutboxItem,
  type EmailOutboxStatus,
} from '../../../api/emailOutbox'
import {
  useEmailOutboxQuery,
  useEmailOutboxItemQuery,
  useRetryEmailOutboxMutation,
  useCancelEmailOutboxMutation,
} from '../../../queries/admin'
import { parseApiError } from '../../../utils/parseApiError'
import { useCursorPager } from '../../../composables/useCursorPager'

const { t } = useI18n()
const message = useMessage()

const STATUS_LABELS: Record<EmailOutboxStatus, string> = {
  PENDING: 'admin.emailOutbox.status.pending',
  SENDING: 'admin.emailOutbox.status.sending',
  SENT: 'admin.emailOutbox.status.sent',
  FAILED: 'admin.emailOutbox.status.failed',
  DLQ: 'admin.emailOutbox.status.dlq',
  CANCELLED: 'admin.emailOutbox.status.cancelled',
}

const STATUS_TYPE: Record<EmailOutboxStatus, 'default' | 'info' | 'success' | 'warning' | 'error'> = {
  PENDING: 'info',
  SENDING: 'info',
  SENT: 'success',
  FAILED: 'warning',
  DLQ: 'error',
  CANCELLED: 'default',
}

const filters = reactive<EmailOutboxFilters>({
  status: '',
  kind: '',
  to_email: '',
  q: '',
})

// audit M2: гибридная page→cursor пагинация (useCursorPager). Email-outbox —
// быстрорастущая таблица, keyset критичен на больших объёмах.
const cursorPager = useCursorPager(50)
const committedFilters = shallowRef<EmailOutboxFilters>({})

const committedParams = computed<EmailOutboxFilters>(() => ({
  ...committedFilters.value,
  ...cursorPager.buildParams(),
}))
const { data: listData, isLoading: loading } = useEmailOutboxQuery(committedParams)

// audit M2: сохраняем next_cursor из ответа для следующей страницы.
watch(() => listData.value, (data) => {
  if (data) cursorPager.consumeResponse(data.next_cursor)
})

const items = computed<EmailOutboxItem[]>(() => listData.value?.items ?? [])
const total = computed(() => listData.value?.total ?? 0)
const counts = computed<Record<string, number> | null>(() => listData.value?.counts_30d ?? null)

const selectedId = ref<string | null>(null)
const detailOpen = ref(false)
const { data: detail } = useEmailOutboxItemQuery(selectedId)

const retryMutation = useRetryEmailOutboxMutation()
const cancelMutation = useCancelEmailOutboxMutation()
const acting = computed(() => retryMutation.isPending.value || cancelMutation.isPending.value)

const dlqCount = computed(() => counts.value?.DLQ ?? 0)

const statusOptions = computed(() =>
  (Object.keys(STATUS_LABELS) as EmailOutboxStatus[]).map((s) => ({
    label: t(STATUS_LABELS[s]),
    value: s,
  })),
)

const kindOptions = [
  { label: t('admin.emailOutbox.kinds.meeting'), value: 'meeting' },
  { label: t('admin.emailOutbox.kinds.news'), value: 'news' },
  { label: t('admin.emailOutbox.kinds.kb_suggestion'), value: 'kb_suggestion' },
  { label: t('admin.emailOutbox.kinds.generic'), value: 'generic' },
]

const pagination = computed(() => ({
  page: cursorPager.pager.page,
  pageSize: cursorPager.pager.pageSize,
  itemCount: total.value,
  showSizePicker: false,
}))

function formatDate(s: string | null): string {
  if (!s) return ''
  try {
    return new Date(s).toLocaleString()
  } catch {
    return s
  }
}

function canRetry(s: EmailOutboxStatus) {
  return s === 'FAILED' || s === 'DLQ' || s === 'CANCELLED' || s === 'SENT'
}
function canCancel(s: EmailOutboxStatus) {
  return s === 'PENDING' || s === 'FAILED' || s === 'DLQ'
}

const columns = computed(() => [
  {
    title: t('admin.emailOutbox.cols.status'),
    key: 'status',
    width: 110,
    render: (row: EmailOutboxItem) =>
      h(
        NTag,
        { type: STATUS_TYPE[row.status], size: 'small' },
        { default: () => t(STATUS_LABELS[row.status]) },
      ),
  },
  { title: t('admin.emailOutbox.cols.kind'), key: 'kind', width: 120 },
  { title: t('admin.emailOutbox.cols.to'), key: 'to_email', ellipsis: { tooltip: true } },
  { title: t('admin.emailOutbox.cols.subject'), key: 'subject', ellipsis: { tooltip: true } },
  {
    title: t('admin.emailOutbox.cols.attempts'),
    key: 'attempts',
    width: 80,
    render: (row: EmailOutboxItem) => `${row.attempts}/${row.max_attempts}`,
  },
  {
    title: t('admin.emailOutbox.cols.lastError'),
    key: 'last_error',
    ellipsis: { tooltip: true },
    render: (row: EmailOutboxItem) =>
      row.last_error ? `${row.last_error_type ?? ''}: ${row.last_error}` : '',
  },
  {
    title: t('admin.emailOutbox.cols.created'),
    key: 'created_at',
    width: 160,
    render: (row: EmailOutboxItem) => formatDate(row.created_at),
  },
  {
    title: t('admin.emailOutbox.cols.actions'),
    key: 'actions',
    width: 220,
    render: (row: EmailOutboxItem) =>
      h('div', { style: 'display:flex;gap:6px' }, [
        h(
          NButton,
          { size: 'tiny', onClick: () => openDetail(row.id) },
          { default: () => t('admin.emailOutbox.actions.details') },
        ),
        canRetry(row.status)
          ? h(
              NButton,
              { size: 'tiny', type: 'primary', onClick: () => onRetry(row.id) },
              { default: () => t('admin.emailOutbox.actions.retry') },
            )
          : null,
        canCancel(row.status)
          ? h(
              NButton,
              { size: 'tiny', onClick: () => onCancel(row.id) },
              { default: () => t('admin.emailOutbox.actions.cancel') },
            )
          : null,
      ]),
  },
])

function activeParams(): EmailOutboxFilters {
  const out: EmailOutboxFilters = { limit: filters.limit ?? 50, offset: 0 }
  if (filters.status) out.status = filters.status
  if (filters.kind) out.kind = filters.kind
  if (filters.to_email) out.to_email = filters.to_email
  if (filters.q) out.q = filters.q
  return out
}

function reload() {
  // audit M2: смена фильтров сбрасывает кеш курсоров (невалидны для нового набора).
  cursorPager.reset()
  committedFilters.value = activeParams()
}

function onPageChange(page: number) {
  cursorPager.goToPage(page)
}

function resetFilters() {
  filters.status = ''
  filters.kind = ''
  filters.to_email = ''
  filters.q = ''
  reload()
}

function openDetail(id: string) {
  selectedId.value = id
  detailOpen.value = true
}

async function onRetry(id: string) {
  try {
    await retryMutation.mutateAsync(id)
    message.success(t('admin.emailOutbox.actions.retryDone'))
    detailOpen.value = false
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

async function onCancel(id: string) {
  try {
    await cancelMutation.mutateAsync(id)
    message.success(t('admin.emailOutbox.actions.cancelDone'))
    detailOpen.value = false
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}
</script>

<style scoped>
@import '../admin-tabs.css';

.outbox-stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  align-items: center;
}
.outbox-stat {
  font-variant-numeric: tabular-nums;
}
.outbox-dlq-alert {
  color: #c0392b;
  font-weight: 600;
  margin-left: 8px;
}
.outbox-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.outbox-detail__row {
  margin-bottom: 8px;
}
.outbox-detail__error {
  color: #c0392b;
}
.outbox-detail__pre {
  background: #f4f4f4;
  border-radius: 4px;
  padding: 8px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 360px;
  overflow: auto;
}
.modal-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
