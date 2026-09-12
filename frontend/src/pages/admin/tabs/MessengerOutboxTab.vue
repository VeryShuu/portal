<template>
  <div class="outbox-wrap">
    <div
      class="branding-section__hint"
      style="margin-bottom:12px"
    >
      {{ t('admin.messengerOutbox.hint') }}
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
        {{ t('admin.messengerOutbox.dlqAlert', { n: dlqCount }) }}
      </span>
    </div>

    <div class="outbox-filters">
      <n-select
        v-model:value="filters.status"
        :options="statusOptions"
        :placeholder="t('admin.messengerOutbox.filters.statusPlaceholder')"
        clearable
        size="small"
        style="min-width:160px"
      />
      <n-select
        v-model:value="filters.provider"
        :options="providerOptions"
        :placeholder="t('admin.messengerOutbox.filters.providerPlaceholder')"
        clearable
        size="small"
        style="min-width:180px"
      />
      <n-input
        v-model:value="filters.chat_id"
        :placeholder="t('admin.messengerOutbox.filters.chatPlaceholder')"
        clearable
        size="small"
        :maxlength="255"
        style="min-width:220px"
      />
      <n-input
        v-model:value="filters.q"
        :placeholder="t('admin.messengerOutbox.filters.search')"
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
        {{ t('admin.messengerOutbox.filters.apply') }}
      </n-button>
      <n-button
        size="small"
        @click="resetFilters"
      >
        {{ t('admin.messengerOutbox.filters.reset') }}
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
      :row-key="(row: MessengerOutboxItem) => row.id"
      size="small"
      striped
      class="data-table"
      @update:page="onPageChange"
    />

    <n-modal
      v-model:show="detailOpen"
      preset="card"
      :title="t('admin.messengerOutbox.detailTitle')"
      style="width:760px;max-width:96vw"
      :mask-closable="true"
    >
      <div
        v-if="detail"
        class="outbox-detail"
      >
        <div class="outbox-detail__row">
          <strong>{{ t('admin.messengerOutbox.cols.status') }}:</strong>
          <n-tag
            :type="STATUS_TYPE[detail.status]"
            size="small"
          >
            {{ t(STATUS_LABELS[detail.status]) }}
          </n-tag>
        </div>
        <div class="outbox-detail__row">
          <strong>{{ t('admin.messengerOutbox.cols.provider') }}:</strong>
          {{ providerLabel(detail.provider) }}
        </div>
        <div class="outbox-detail__row">
          <strong>{{ t('admin.messengerOutbox.cols.chat') }}:</strong>
          {{ detail.chat_id }}
        </div>
        <div class="outbox-detail__row">
          <strong>{{ t('admin.messengerOutbox.cols.attempts') }}:</strong>
          {{ detail.attempts }} / {{ detail.max_attempts }}
        </div>
        <div
          v-if="detail.next_attempt_at"
          class="outbox-detail__row"
        >
          <strong>{{ t('admin.messengerOutbox.cols.nextAttempt') }}:</strong>
          {{ formatDate(detail.next_attempt_at) }}
        </div>
        <div
          v-if="detail.last_error"
          class="outbox-detail__row outbox-detail__error"
        >
          <strong>{{ t('admin.messengerOutbox.lastError') }}
            ({{ detail.last_error_type }} / {{ detail.last_error_class }}):</strong>
          <pre class="outbox-detail__pre">{{ detail.last_error }}</pre>
        </div>
        <details class="outbox-detail__body">
          <summary>{{ t('admin.messengerOutbox.showText') }}</summary>
          <pre class="outbox-detail__pre">{{ detail.text }}</pre>
        </details>
        <details
          v-if="hasPayload"
          class="outbox-detail__body"
        >
          <summary>{{ t('admin.messengerOutbox.showPayload') }}</summary>
          <pre class="outbox-detail__pre">{{ payloadPretty }}</pre>
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
            {{ t('admin.messengerOutbox.actions.retry') }}
          </n-button>
          <n-button
            v-if="detail && canCancel(detail.status)"
            :loading="acting"
            @click="onCancel(detail.id)"
          >
            {{ t('admin.messengerOutbox.actions.cancel') }}
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
  type MessengerOutboxFilters,
  type MessengerOutboxItem,
  type MessengerOutboxStatus,
  type MessengerProvider,
} from '../../../api/messengerOutbox'
import {
  useMessengerOutboxQuery,
  useMessengerOutboxItemQuery,
  useRetryMessengerOutboxMutation,
  useCancelMessengerOutboxMutation,
} from '../../../queries/admin'
import { parseApiError } from '../../../utils/parseApiError'
import { useCursorPager } from '../../../composables/useCursorPager'

const { t } = useI18n()
const message = useMessage()

const STATUS_LABELS: Record<MessengerOutboxStatus, string> = {
  PENDING: 'admin.messengerOutbox.status.pending',
  SENDING: 'admin.messengerOutbox.status.sending',
  SENT: 'admin.messengerOutbox.status.sent',
  FAILED: 'admin.messengerOutbox.status.failed',
  DLQ: 'admin.messengerOutbox.status.dlq',
  CANCELLED: 'admin.messengerOutbox.status.cancelled',
}

const STATUS_TYPE: Record<MessengerOutboxStatus, 'default' | 'info' | 'success' | 'warning' | 'error'> = {
  PENDING: 'info',
  SENDING: 'info',
  SENT: 'success',
  FAILED: 'warning',
  DLQ: 'error',
  CANCELLED: 'default',
}

const PROVIDER_LABELS: Record<MessengerProvider, string> = {
  max: 'admin.messengerOutbox.providers.max',
  matrix: 'admin.messengerOutbox.providers.matrix',
}

const filters = reactive<MessengerOutboxFilters>({
  status: '',
  provider: '',
  chat_id: '',
  q: '',
})

// Гибридная page→cursor пагинация (как email-outbox): keyset по
// ix_messenger_outbox_created_id (миграция 097).
const cursorPager = useCursorPager(50)
const committedFilters = shallowRef<MessengerOutboxFilters>({})

const committedParams = computed<MessengerOutboxFilters>(() => ({
  ...committedFilters.value,
  ...cursorPager.buildParams(),
}))
const { data: listData, isLoading: loading } = useMessengerOutboxQuery(committedParams)

watch(() => listData.value, (data) => {
  if (data) cursorPager.consumeResponse(data.next_cursor)
})

const items = computed<MessengerOutboxItem[]>(() => listData.value?.items ?? [])
const total = computed(() => listData.value?.total ?? 0)
const counts = computed<Record<string, number> | null>(() => listData.value?.counts_30d ?? null)

const selectedId = ref<string | null>(null)
const detailOpen = ref(false)
const { data: detail } = useMessengerOutboxItemQuery(selectedId)

const retryMutation = useRetryMessengerOutboxMutation()
const cancelMutation = useCancelMessengerOutboxMutation()
const acting = computed(() => retryMutation.isPending.value || cancelMutation.isPending.value)

const dlqCount = computed(() => counts.value?.DLQ ?? 0)

const statusOptions = computed(() =>
  (Object.keys(STATUS_LABELS) as MessengerOutboxStatus[]).map((s) => ({
    label: t(STATUS_LABELS[s]),
    value: s,
  })),
)

const providerOptions = computed(() =>
  (Object.keys(PROVIDER_LABELS) as MessengerProvider[]).map((p) => ({
    label: t(PROVIDER_LABELS[p]),
    value: p,
  })),
)

function providerLabel(p: MessengerProvider): string {
  return t(PROVIDER_LABELS[p] ?? p)
}

const payloadPretty = computed(() => {
  const p = detail.value?.payload
  if (!p || Object.keys(p).length === 0) return ''
  try {
    return JSON.stringify(p, null, 2)
  } catch {
    return String(p)
  }
})
const hasPayload = computed(() => !!payloadPretty.value)

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

function canRetry(s: MessengerOutboxStatus) {
  return s === 'FAILED' || s === 'DLQ' || s === 'CANCELLED' || s === 'SENT'
}
function canCancel(s: MessengerOutboxStatus) {
  return s === 'PENDING' || s === 'FAILED' || s === 'DLQ'
}

const columns = computed(() => [
  {
    title: t('admin.messengerOutbox.cols.status'),
    key: 'status',
    width: 110,
    render: (row: MessengerOutboxItem) =>
      h(
        NTag,
        { type: STATUS_TYPE[row.status], size: 'small' },
        { default: () => t(STATUS_LABELS[row.status]) },
      ),
  },
  {
    title: t('admin.messengerOutbox.cols.provider'),
    key: 'provider',
    width: 110,
    render: (row: MessengerOutboxItem) => providerLabel(row.provider),
  },
  { title: t('admin.messengerOutbox.cols.chat'), key: 'chat_id', ellipsis: { tooltip: true } },
  { title: t('admin.messengerOutbox.cols.text'), key: 'text_preview', ellipsis: { tooltip: true } },
  {
    title: t('admin.messengerOutbox.cols.attempts'),
    key: 'attempts',
    width: 80,
    render: (row: MessengerOutboxItem) => `${row.attempts}/${row.max_attempts}`,
  },
  {
    title: t('admin.messengerOutbox.cols.lastError'),
    key: 'last_error',
    ellipsis: { tooltip: true },
    render: (row: MessengerOutboxItem) =>
      row.last_error ? `${row.last_error_type ?? ''}: ${row.last_error}` : '',
  },
  {
    title: t('admin.messengerOutbox.cols.created'),
    key: 'created_at',
    width: 160,
    render: (row: MessengerOutboxItem) => formatDate(row.created_at),
  },
  {
    title: t('admin.messengerOutbox.cols.actions'),
    key: 'actions',
    width: 220,
    render: (row: MessengerOutboxItem) =>
      h('div', { style: 'display:flex;gap:6px' }, [
        h(
          NButton,
          { size: 'tiny', onClick: () => openDetail(row.id) },
          { default: () => t('admin.messengerOutbox.actions.details') },
        ),
        canRetry(row.status)
          ? h(
              NButton,
              { size: 'tiny', type: 'primary', onClick: () => onRetry(row.id) },
              { default: () => t('admin.messengerOutbox.actions.retry') },
            )
          : null,
        canCancel(row.status)
          ? h(
              NButton,
              { size: 'tiny', onClick: () => onCancel(row.id) },
              { default: () => t('admin.messengerOutbox.actions.cancel') },
            )
          : null,
      ]),
  },
])

function activeParams(): MessengerOutboxFilters {
  const out: MessengerOutboxFilters = { limit: filters.limit ?? 50, offset: 0 }
  if (filters.status) out.status = filters.status
  if (filters.provider) out.provider = filters.provider
  if (filters.chat_id) out.chat_id = filters.chat_id
  if (filters.q) out.q = filters.q
  return out
}

function reload() {
  // Смена фильтров сбрасывает кеш курсоров (невалидны для нового набора).
  cursorPager.reset()
  committedFilters.value = activeParams()
}

function onPageChange(page: number) {
  cursorPager.goToPage(page)
}

function resetFilters() {
  filters.status = ''
  filters.provider = ''
  filters.chat_id = ''
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
    message.success(t('admin.messengerOutbox.actions.retryDone'))
    detailOpen.value = false
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

async function onCancel(id: string) {
  try {
    await cancelMutation.mutateAsync(id)
    message.success(t('admin.messengerOutbox.actions.cancelDone'))
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
