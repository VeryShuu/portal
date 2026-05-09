<template>
  <div class="audit-wrap">
    <div class="branding-section__hint" style="margin-bottom:12px">{{ t('admin.audit.hint') }}</div>

    <div class="audit-filters">
      <n-select
        v-model:value="auditFilters.event_type"
        :options="auditEventTypeOptions"
        :placeholder="t('admin.audit.filters.eventTypePlaceholder')"
        clearable
        filterable
        size="small"
        style="min-width:200px"
      />
      <n-input
        v-model:value="auditFilters.user_id"
        :placeholder="t('admin.audit.filters.userIdPlaceholder')"
        clearable
        size="small"
        :maxlength="36"
        :status="userIdInvalid ? 'error' : undefined"
        style="min-width:240px"
      />
      <n-input
        v-model:value="auditFilters.ip_address"
        :placeholder="t('admin.audit.filters.ipPlaceholder')"
        clearable
        size="small"
        :maxlength="64"
        style="min-width:140px"
      />
      <n-input
        v-model:value="auditFilters.q"
        :placeholder="t('admin.audit.filters.search')"
        clearable
        size="small"
        :maxlength="200"
        style="min-width:240px;flex:1"
      />
      <n-button size="small" type="primary" @click="reloadAudit">
        {{ t('admin.audit.filters.apply') }}
      </n-button>
      <n-button size="small" @click="resetAuditFilters">
        {{ t('admin.audit.filters.reset') }}
      </n-button>
      <n-button size="small" @click="exportAuditCsv">
        <template #icon><n-icon><DownloadOutline /></n-icon></template>
        {{ t('admin.audit.exportCsv') }}
      </n-button>
    </div>

    <div class="audit-meta" v-if="auditTotal !== null || auditQueue">
      <span v-if="auditTotal !== null">{{ t('admin.audit.totalRows', { n: auditTotal }) }}</span>
      <span v-if="auditQueue" class="audit-queue">
        {{ t('admin.audit.queueDepth') }}:
        {{ t('admin.audit.queuePending', { n: auditQueue.pending }) }} ·
        {{ t('admin.audit.queueProcessing', { n: auditQueue.processing }) }}
      </span>
    </div>

    <n-data-table
      :columns="auditColumns"
      :data="auditEvents"
      :loading="loadingAudit"
      :pagination="auditPagination"
      :remote="true"
      :row-key="(row: AuditEvent) => row.id"
      size="small"
      striped
      class="data-table"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, h, shallowRef } from 'vue'
import { BASE_URL } from '../../../api'
import { ofetch } from 'ofetch'
import { useI18n } from 'vue-i18n'
import { NButton, NDataTable, NInput, NSelect, NIcon, NTag, useMessage, type DataTableColumns } from 'naive-ui'
import { DownloadOutline } from '@vicons/ionicons5'
import {
  type AuditEvent, type AuditFilters,
} from '../../../api/audit'
import { useAuditEventTypesQuery, useAuditQueueQuery, useAuditEventsQuery } from '../../../queries/admin'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const { t } = useI18n()
const message = useMessage()

const { data: auditEventTypesData } = useAuditEventTypesQuery()
const { data: auditQueueData } = useAuditQueueQuery()

const auditEventTypes = computed(() => auditEventTypesData.value ?? [])
const auditQueue = computed(() => auditQueueData.value ?? null)

const auditFilters = reactive<AuditFilters>({
  user_id: '',
  event_type: '',
  resource_type: '',
  ip_address: '',
  date_from: '',
  date_to: '',
  q: '',
})

const paginationState = reactive({ page: 1, pageSize: 50 })

const committedParams = shallowRef<AuditFilters & { limit: number; offset: number }>({
  limit: 50,
  offset: 0,
})

const { data: auditData, isLoading: loadingAudit } = useAuditEventsQuery(committedParams)

const auditEvents = computed(() => auditData.value?.items ?? [])
const auditTotal = computed(() => auditData.value?.total ?? null)

const auditPagination = computed(() => ({
  page: paginationState.page,
  pageSize: paginationState.pageSize,
  itemCount: auditData.value?.total ?? 0,
  pageSizes: [25, 50, 100, 200],
  showSizePicker: true,
  onChange: (page: number) => {
    paginationState.page = page
    committedParams.value = { ...committedParams.value, offset: (page - 1) * paginationState.pageSize }
  },
  onUpdatePageSize: (size: number) => {
    paginationState.page = 1
    paginationState.pageSize = size
    committedParams.value = { ...committedParams.value, limit: size, offset: 0 }
  },
}))

const auditEventTypeOptions = computed(() =>
  auditEventTypes.value.map((et) => ({ label: et, value: et })),
)

const userIdInvalid = computed(() => {
  const v = auditFilters.user_id
  return !!v && !UUID_RE.test(v)
})

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return ''
  try { return new Date(iso).toLocaleString() } catch { return iso }
}

const auditColumns = computed<DataTableColumns<AuditEvent>>(() => [
  {
    title: t('admin.audit.columns.createdAt'),
    key: 'created_at',
    width: 170,
    render: (row) => (row.created_at ? formatDateTime(row.created_at) : '—'),
  },
  {
    title: t('admin.audit.columns.eventType'),
    key: 'event_type',
    width: 200,
    render: (row) => h(NTag, { size: 'small', bordered: false }, { default: () => row.event_type }),
  },
  {
    title: t('admin.audit.columns.userEmail'),
    key: 'user_email',
    ellipsis: { tooltip: true },
    render: (row) => row.user_email || '—',
  },
  {
    title: t('admin.audit.columns.resource'),
    key: 'resource',
    ellipsis: { tooltip: true },
    render: (row) => {
      if (!row.resource_type) return '—'
      const title = row.resource_title ? ` · ${row.resource_title}` : ''
      return `${row.resource_type}${row.resource_id ? `#${row.resource_id}` : ''}${title}`
    },
  },
  {
    title: t('admin.audit.columns.ip'),
    key: 'ip_address',
    width: 130,
    render: (row) => row.ip_address || '—',
  },
  {
    title: t('admin.audit.columns.metadata'),
    key: 'metadata',
    ellipsis: { tooltip: true },
    render: (row) => {
      try {
        const json = JSON.stringify(row.metadata ?? {})
        return json.length > 200 ? json.slice(0, 200) + '…' : json
      } catch {
        return ''
      }
    },
  },
])

function _activeAuditFilters(): AuditFilters {
  const out: AuditFilters = {}
  for (const key of ['user_id', 'event_type', 'resource_type', 'ip_address', 'date_from', 'date_to', 'q'] as const) {
    const v = auditFilters[key]
    if (v !== undefined && v !== null && String(v).length > 0) {
      out[key] = v as string
    }
  }
  return out
}

function reloadAudit() {
  if (userIdInvalid.value) {
    message.error(t('admin.audit.filters.userIdInvalid'))
    return
  }
  paginationState.page = 1
  committedParams.value = {
    ..._activeAuditFilters(),
    limit: paginationState.pageSize,
    offset: 0,
  }
}

function resetAuditFilters() {
  auditFilters.user_id = ''
  auditFilters.event_type = ''
  auditFilters.resource_type = ''
  auditFilters.ip_address = ''
  auditFilters.date_from = ''
  auditFilters.date_to = ''
  auditFilters.q = ''
  reloadAudit()
}

async function exportAuditCsv() {
  try {
    const filters = _activeAuditFilters()
    const query: Record<string, string | number> = {}
    for (const [k, v] of Object.entries(filters)) {
      if (v !== undefined && v !== null && v !== '') query[k] = v as string | number
    }
    const blob = await ofetch('/audit/export.csv', {
      baseURL: BASE_URL,
      credentials: 'include',
      responseType: 'blob',
      query,
      timeout: 60_000,
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `audit-${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch {
    message.error(t('errors.generic'))
  }
}


</script>

<style scoped>
@import '../admin-tabs.css';
</style>
