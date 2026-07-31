<template>
  <section class="branding-section">
    <div class="erp-sync__runs-header">
      <h3 class="branding-section__title">
        {{ t('admin.erpSync.runs.title') }}
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
      :row-key="(row: ErpSyncRun) => row.id"
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
import type { ErpSyncRun } from '../../api/erpSync'
import { useErpSyncRunsQuery } from '../../queries/erpSync'

const { t } = useI18n()

const paginationState = reactive({ page: 1, pageSize: 20 })
const committedParams = shallowRef({ limit: 20, offset: 0 })

const { data: runsData, isLoading: loading, refetch } = useErpSyncRunsQuery(committedParams)

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

function statusTagType(status: ErpSyncRun['status']) {
  if (status === 'success') return 'success'
  if (status === 'partial') return 'warning'
  if (status === 'failed') return 'error'
  return 'default'
}

function statusLabel(status: ErpSyncRun['status']) {
  return t(`admin.erpSync.runs.status.${status}`)
}

function formatDateTime(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

const columns = computed<DataTableColumns<ErpSyncRun>>(() => [
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
    width: 120,
    render: (row) =>
      h(
        NTag,
        { type: statusTagType(row.status), size: 'small', bordered: false },
        { default: () => statusLabel(row.status) },
      ),
  },
  {
    title: t('admin.erpSync.runs.trigger'),
    key: 'triggered_by',
    width: 100,
    render: (row) => t(`admin.erpSync.runs.trigger.${row.triggered_by}`),
  },
  {
    title: t('admin.erpSync.runs.updated'),
    key: 'rows_updated',
    width: 90,
    render: (row) => String(row.rows_updated ?? 0),
  },
  {
    title: t('admin.erpSync.runs.problems'),
    key: 'problems',
    width: 100,
    render: (row) => {
      const problems =
        (row.rows_unmatched ?? 0) +
        (row.rows_ambiguous ?? 0) +
        (row.conflicts ?? 0) +
        (row.errors ?? 0)
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

function renderReport(row: ErpSyncRun) {
  const r = row.report ?? {}
  const parts: ReturnType<typeof h>[] = []

  const changed = r.changed ?? []
  if (changed.length) {
    parts.push(
      h('div', { class: 'erp-sync__report-section' }, [
        h('h5', {}, t('admin.erpSync.report.changed', { count: changed.length })),
        ...changed.map((c) =>
          h('div', { class: 'erp-sync__report-row' }, [
            h('span', { class: 'erp-sync__report-fio' }, c.fio),
            ...Object.entries(c.fields).map(([field, diff]) =>
              h('div', { class: 'erp-sync__report-diff' }, [
                h('span', { class: 'erp-sync__report-field' }, fieldLabel(field)),
                h(
                  'span',
                  { class: 'erp-sync__report-old' },
                  formatDiffValue(diff.old),
                ),
                ' → ',
                h(
                  'span',
                  { class: 'erp-sync__report-new' },
                  formatDiffValue(diff.new),
                ),
              ]),
            ),
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
          h('div', { class: 'erp-sync__report-row' }, `${u.fio} (${u.birth_date})`),
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

  const conflicts = r.conflicts ?? []
  if (conflicts.length) {
    parts.push(
      h('div', { class: 'erp-sync__report-section' }, [
        h('h5', {}, t('admin.erpSync.report.conflicts', { count: conflicts.length })),
        ...conflicts.map((c) =>
          h('div', { class: 'erp-sync__report-row' }, [
            `${c.fio}: `,
            c.variants.map((v) => `${v.birth_date}/${genderLabel(v.gender)}`).join('; '),
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

function fieldLabel(field: string) {
  return t(`admin.erpSync.report.fields.${field}`, field)
}

function genderLabel(g: string) {
  if (g === 'male') return t('admin.erpSync.report.male')
  if (g === 'female') return t('admin.erpSync.report.female')
  return g
}

function formatDiffValue(v: unknown) {
  if (v === null || v === undefined) return '—'
  return String(v)
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
.erp-sync__report-diff {
  padding-left: 16px;
  font-size: 12px;
  color: var(--color-text-secondary, #666);
}
.erp-sync__report-old {
  text-decoration: line-through;
  opacity: 0.7;
}
.erp-sync__report-new {
  font-weight: 600;
  color: var(--color-brand-navy, #1f3a5f);
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
