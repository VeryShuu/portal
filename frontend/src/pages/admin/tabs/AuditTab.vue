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
import { ref, computed, reactive, onMounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDataTable, NInput, NSelect, NIcon, NTag, useMessage, type DataTableColumns } from 'naive-ui'
import { DownloadOutline } from '@vicons/ionicons5'
import {
  fetchAuditEvents, fetchAuditEventTypes, fetchAuditQueueDepth, buildAuditCsvUrl,
  type AuditEvent, type AuditFilters,
} from '../../../api/audit'

const { t } = useI18n()
const message = useMessage()

const auditEvents = ref<AuditEvent[]>([])
const loadingAudit = ref(false)
const auditTotal = ref<number | null>(null)
const auditEventTypes = ref<string[]>([])
const auditQueue = ref<{ pending: number; processing: number } | null>(null)

const auditFilters = reactive<AuditFilters>({
  user_id: '',
  event_type: '',
  resource_type: '',
  ip_address: '',
  date_from: '',
  date_to: '',
  q: '',
})

const auditPagination = reactive({
  page: 1,
  pageSize: 50,
  itemCount: 0,
  pageSizes: [25, 50, 100, 200],
  showSizePicker: true,
  onChange: (page: number) => {
    auditPagination.page = page
    void loadAudit()
  },
  onUpdatePageSize: (size: number) => {
    auditPagination.pageSize = size
    auditPagination.page = 1
    void loadAudit()
  },
})

const auditEventTypeOptions = computed(() =>
  auditEventTypes.value.map((et) => ({ label: et, value: et })),
)

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

async function loadAudit() {
  loadingAudit.value = true
  try {
    const filters = _activeAuditFilters()
    const limit = auditPagination.pageSize
    const offset = (auditPagination.page - 1) * limit
    const res = await fetchAuditEvents({ ...filters, limit, offset })
    auditEvents.value = res.items
    auditTotal.value = res.total
    auditPagination.itemCount = res.total
  } catch (e: unknown) {
    message.error(e instanceof Error ? e.message : t('errors.generic'))
  } finally {
    loadingAudit.value = false
  }
}

async function reloadAudit() {
  auditPagination.page = 1
  await loadAudit()
}

function resetAuditFilters() {
  auditFilters.user_id = ''
  auditFilters.event_type = ''
  auditFilters.resource_type = ''
  auditFilters.ip_address = ''
  auditFilters.date_from = ''
  auditFilters.date_to = ''
  auditFilters.q = ''
  void reloadAudit()
}

async function loadAuditEventTypes() {
  try {
    auditEventTypes.value = await fetchAuditEventTypes()
  } catch {
    auditEventTypes.value = []
  }
}

async function loadAuditQueue() {
  try {
    auditQueue.value = await fetchAuditQueueDepth()
  } catch {
    auditQueue.value = null
  }
}

function exportAuditCsv() {
  const url = buildAuditCsvUrl(_activeAuditFilters())
  window.open(url, '_blank', 'noopener,noreferrer')
}

onMounted(async () => {
  await Promise.all([loadAuditEventTypes(), loadAuditQueue(), reloadAudit()])
})
</script>

<style scoped>
@import '../admin-tabs.css';
</style>
