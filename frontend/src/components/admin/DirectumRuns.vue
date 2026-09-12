<template>
  <section class="branding-section">
    <div class="directum__runs-header">
      <h3 class="branding-section__title">
        {{ t('admin.directum.runs.title') }}
      </h3>
      <n-button
        size="small"
        :loading="false"
        @click="refresh"
      >
        {{ t('admin.directum.runs.refresh') }}
      </n-button>
    </div>

    <n-data-table
      :columns="columns"
      :data="runs"
      :loading="loading"
      :pagination="paginationReactive"
      :remote="true"
      :row-key="(row: DirectumRun) => row.id"
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
import type { DirectumRun } from '../../api/directum'
import { useDirectumRunsQuery } from '../../queries/directum'

const { t } = useI18n()

const paginationState = reactive({ page: 1, pageSize: 20 })
const committedParams = shallowRef({ limit: 20, offset: 0 })

const { data: runsData, isLoading: loading, refetch } = useDirectumRunsQuery(committedParams)

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

function statusTagType(status: DirectumRun['status']) {
  if (status === 'success') return 'success'
  if (status === 'partial') return 'warning'
  if (status === 'failed') return 'error'
  return 'default'
}

function statusLabel(status: DirectumRun['status']) {
  return t(`admin.directum.runs.status.${status}`)
}

function formatDateTime(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

const columns = computed<DataTableColumns<DirectumRun>>(() => [
  {
    type: 'expand',
    expandable: () => true,
    renderExpand: (row) => h('div', { class: 'directum__report' }, [renderReport(row)]),
  },
  {
    title: '#',
    key: 'id',
    width: 60,
  },
  {
    title: t('admin.directum.runs.startedAt'),
    key: 'started_at',
    width: 160,
    render: (row) => formatDateTime(row.started_at),
  },
  {
    title: t('admin.directum.runs.status.label'),
    key: 'status',
    width: 140,
    render: (row) =>
      h(
        NTag,
        { type: statusTagType(row.status), size: 'small', bordered: false },
        { default: () => statusLabel(row.status) },
      ),
  },
  {
    title: t('admin.directum.runs.triggeredBy'),
    key: 'triggered_by',
    width: 110,
    render: (row) => t(`admin.directum.runs.trigger.${row.triggered_by}`),
  },
  {
    title: t('admin.directum.runs.tasks'),
    key: 'tasks_total',
    width: 80,
    render: (row) => String(row.tasks_total ?? 0),
  },
  {
    title: t('admin.directum.runs.notified'),
    key: 'users_notified',
    width: 110,
    render: (row) => String(row.users_notified ?? 0),
  },
  {
    title: t('admin.directum.runs.problems'),
    key: 'problems',
    width: 110,
    render: (row) => {
      const problems =
        (row.users_unmatched ?? 0) + (row.users_ambiguous ?? 0) + (row.errors ?? 0)
      return problems > 0
        ? h('span', { class: 'directum__problems' }, String(problems))
        : '0'
    },
  },
])

function renderReport(row: DirectumRun) {
  const r = row.report ?? {}
  const parts: ReturnType<typeof h>[] = []

  const notified = r.notified ?? []
  if (notified.length) {
    parts.push(reportSection(
      t('admin.directum.report.notified', { count: notified.length }),
      notified.map((n) => pairLine(n)),
    ))
  }

  const skippedOptIn = r.skipped_opt_in ?? []
  if (skippedOptIn.length) {
    parts.push(reportSection(
      t('admin.directum.report.skippedOptIn', { count: skippedOptIn.length }),
      skippedOptIn.map((n) => pairLine(n)),
    ))
  }

  const unmatched = r.unmatched ?? []
  if (unmatched.length) {
    parts.push(reportSection(
      t('admin.directum.report.unmatched', { count: unmatched.length }),
      unmatched.map((n) => pairLine(n)),
    ))
  }

  const ambiguous = r.ambiguous ?? []
  if (ambiguous.length) {
    parts.push(reportSection(
      t('admin.directum.report.ambiguous', { count: ambiguous.length }),
      ambiguous.map((a) =>
        `${a.fio} → ${a.candidates.map((c) => c.full_name).join(', ')}`,
      ),
    ))
  }

  if (r.matrix_disabled) {
    parts.push(h('p', { class: 'directum__report-warn' }, t('admin.directum.report.matrixDisabled')))
  }

  if (r.error) {
    parts.push(h('p', { class: 'directum__report-warn' }, `${t('admin.directum.report.error')}: ${r.error}`))
  }

  if (!parts.length) {
    parts.push(h('p', { class: 'directum__report-empty' }, t('admin.directum.report.empty')))
  }

  return parts
}

function reportSection(title: string, lines: string[]) {
  return h('div', { class: 'directum__report-section' }, [
    h('h5', {}, title),
    ...lines.map((line) => h('div', { class: 'directum__report-row' }, line)),
  ])
}

function pairLine(p: { fio: string; tasks?: number }) {
  return p.tasks !== undefined ? `${p.fio} (${p.tasks})` : p.fio
}

async function refresh() {
  await refetch()
}
</script>

<style scoped>
@import '../../pages/admin/admin-tabs.css';

.directum__runs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.directum__problems {
  font-weight: 600;
  color: #d03050;
}
.directum__report {
  padding: 12px 16px;
  background: var(--color-surface-alt, rgba(0, 0, 0, 0.02));
}
.directum__report h5 {
  margin: 12px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}
.directum__report h5:first-child {
  margin-top: 0;
}
.directum__report-section {
  margin-bottom: 8px;
}
.directum__report-row {
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text);
}
.directum__report-warn {
  margin: 8px 0;
  font-size: 13px;
  color: #b25f0a;
}
.directum__report-empty {
  font-size: 13px;
  color: var(--color-text-secondary, #666);
}
</style>
