<template>
  <section class="branding-section">
    <div class="erp-sync__runs-header">
      <h3 class="branding-section__title">
        {{ t('admin.erpSync.absencesRuns.title') }}
      </h3>
      <n-button
        size="small"
        :loading="false"
        @click="refresh"
      >
        {{ t('admin.erpSync.runs.refresh') }}
      </n-button>
    </div>

    <n-data-table
      :columns="columns"
      :data="runs"
      :loading="loading"
      :pagination="paginationReactive"
      :remote="true"
      :row-key="(row: ErpAbsencesRun) => row.id"
      size="small"
      striped
      class="data-table"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, h, reactive, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDataTable, NTag, type DataTableColumns } from 'naive-ui'
import type { ErpAbsencesRun } from '../../api/erpSync'
import { useErpAbsencesRunsQuery } from '../../queries/erpSync'

const { t } = useI18n()

const paginationState = reactive({ page: 1, pageSize: 20 })
const committedParams = shallowRef({ limit: 20, offset: 0 })

const { data: runsData, isLoading: loading, refetch } = useErpAbsencesRunsQuery(committedParams)

const runs = computed(() => runsData.value?.items ?? [])

const paginationReactive = computed(() => ({
  page: paginationState.page,
  pageSize: paginationState.pageSize,
  itemCount: runsData.value?.total ?? 0,
  pageSizes: [20, 50, 100],
  showSizePicker: true,
  onChange: (page: number) => {
    paginationState.page = page
    committedParams.value = {
      ...committedParams.value,
      offset: (page - 1) * paginationState.pageSize,
    }
  },
  onUpdatePageSize: (size: number) => {
    paginationState.page = 1
    paginationState.pageSize = size
    committedParams.value = { limit: size, offset: 0 }
  },
}))

function statusTagType(status: ErpAbsencesRun['status']) {
  if (status === 'success') return 'success'
  if (status === 'partial') return 'warning'
  if (status === 'failed') return 'error'
  return 'default'
}

function statusLabel(status: ErpAbsencesRun['status']) {
  return t(`admin.erpSync.runs.status.${status}`)
}

function formatDateTime(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function kindLabel(kind: string) {
  return t(`users.profile.absences.kinds.${kind}`, kind)
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString()
}

const columns = computed<DataTableColumns<ErpAbsencesRun>>(() => [
  {
    type: 'expand',
    expandable: () => true,
    renderExpand: (row) => h('div', { class: 'erp-sync__report' }, [renderReport(row)]),
  },
  {
    title: '#',
    key: 'id',
    width: 60,
  },
  {
    title: t('admin.erpSync.runs.startedAt'),
    key: 'started_at',
    width: 160,
    render: (row) => formatDateTime(row.started_at),
  },
  {
    title: t('admin.erpSync.runs.status.label'),
    key: 'status',
    width: 160,
    render: (row) =>
      h(
        NTag,
        { type: statusTagType(row.status), size: 'small', bordered: false },
        { default: () => statusLabel(row.status) },
      ),
  },
  {
    title: t('admin.erpSync.runs.triggeredBy'),
    key: 'triggered_by',
    width: 100,
    render: (row) => t(`admin.erpSync.runs.trigger.${row.triggered_by}`),
  },
  {
    title: t('admin.erpSync.absencesRuns.inserted'),
    key: 'rows_inserted',
    width: 100,
    render: (row) => String(row.rows_inserted ?? 0),
  },
  {
    title: t('admin.erpSync.runs.problems'),
    key: 'problems',
    width: 100,
    render: (row) => {
      const problems =
        (row.rows_unmatched ?? 0) + (row.rows_ambiguous ?? 0) + (row.errors ?? 0)
      return problems > 0
        ? h('span', { class: 'erp-sync__problems' }, String(problems))
        : '0'
    },
  },
  {
    title: t('admin.erpSync.runs.attachment'),
    key: 'attachment_name',
    ellipsis: { tooltip: true },
    render: (row) => row.attachment_name ?? '—',
  },
])

function renderReport(row: ErpAbsencesRun) {
  const r = row.report ?? {}
  const parts: ReturnType<typeof h>[] = []

  const inserted = r.inserted ?? []
  if (inserted.length) {
    parts.push(
      h('div', { class: 'erp-sync__report-section' }, [
        h('h5', {}, t('admin.erpSync.absencesRuns.reportInserted', { count: inserted.length })),
        ...inserted.map((i) =>
          h('div', { class: 'erp-sync__report-row' }, [
            h('span', { class: 'erp-sync__report-fio' }, i.fio),
            ' — ',
            kindLabel(i.kind),
            ` (${formatDate(i.start_date)} – ${formatDate(i.end_date)})`,
          ]),
        ),
      ]),
    )
  }

  const unmatched = r.unmatched ?? []
  if (unmatched.length) {
    parts.push(
      h('div', { class: 'erp-sync__report-section' }, [
        h('h5', {}, t('admin.erpSync.report.unmatched', { count: unmatched.length })),
        ...unmatched.map((u) =>
          h(
            'div',
            { class: 'erp-sync__report-row' },
            `${u.fio} (${kindLabel(u.kind)}, ${formatDate(u.start_date)} – ${formatDate(u.end_date)})`,
          ),
        ),
      ]),
    )
  }

  const ambiguous = r.ambiguous ?? []
  if (ambiguous.length) {
    parts.push(
      h('div', { class: 'erp-sync__report-section' }, [
        h('h5', {}, t('admin.erpSync.report.ambiguous', { count: ambiguous.length })),
        ...ambiguous.map((a) =>
          h('div', { class: 'erp-sync__report-row' }, [
            `${a.fio} → `,
            a.candidates.map((c) => c.full_name).join(', '),
          ]),
        ),
      ]),
    )
  }

  const errors = r.errors ?? []
  if (errors.length) {
    parts.push(
      h('div', { class: 'erp-sync__report-section' }, [
        h('h5', {}, t('admin.erpSync.report.errors', { count: errors.length })),
        ...errors.map((e) =>
          h('div', { class: 'erp-sync__report-row' }, [h('code', {}, e.raw), ` — ${e.reason}`]),
        ),
      ]),
    )
  }

  if (!parts.length) {
    parts.push(h('p', { class: 'erp-sync__report-empty' }, t('admin.erpSync.report.empty')))
  }

  return parts
}

async function refresh() {
  await refetch()
}
</script>

<style scoped>
@import '../../pages/admin/admin-tabs.css';

.erp-sync__runs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.erp-sync__problems {
  font-weight: 600;
  color: #d03050;
}
.erp-sync__report {
  padding: 12px 16px;
  background: var(--color-surface-alt, rgba(0, 0, 0, 0.02));
}
.erp-sync__report h5 {
  margin: 12px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}
.erp-sync__report h5:first-child {
  margin-top: 0;
}
.erp-sync__report-section {
  margin-bottom: 8px;
}
.erp-sync__report-row {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text);
}
.erp-sync__report-fio {
  font-weight: 500;
}
.erp-sync__report-empty {
  font-size: 13px;
  color: var(--color-text-secondary, #666);
}
.erp-sync__report code {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  background: rgba(0, 0, 0, 0.04);
  padding: 1px 4px;
  border-radius: 3px;
}
</style>
