<template>
  <div class="analytics-wrap">
    <div class="tab-toolbar">
      <div class="analytics-meta">
        <span v-if="dashboard">{{ t('admin.analytics.generatedAt', { t: formatDateTime(dashboard.generated_at) }) }}</span>
      </div>
      <div class="analytics-toolbar-actions">
        <n-select
          v-model:value="period"
          class="analytics-period"
          size="small"
          :options="periodOptions"
          :aria-label="t('admin.analytics.period.label')"
        />
        <n-button
          :loading="loadingDashboard"
          @click="loadAnalytics"
        >
          <template #icon>
            <n-icon><SyncOutline /></n-icon>
          </template>
          {{ t('admin.analytics.refresh') }}
        </n-button>
      </div>
    </div>

    <div
      v-if="dashboard"
      class="kpi-grid"
    >
      <div class="kpi-card">
        <div class="kpi-card__title">
          {{ t('admin.analytics.users.title') }}
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.users.total') }}</span><b>{{ dashboard.users.total }}</b>
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.users.active30d') }}</span><b>{{ dashboard.users.active_30d }}</b>
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.users.active1h') }}</span><b>{{ dashboard.users.active_1h }}</b>
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.users.new30d') }}</span><b>{{ dashboard.users.new_30d }}</b>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-card__title">
          {{ t('admin.analytics.engagement.title') }}
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.engagement.wau') }}</span><b>{{ dashboard.activity.wau_7d }}</b>
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.engagement.mau') }}</span><b>{{ dashboard.activity.mau_30d }}</b>
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.content.newsPublished') }}</span><b>{{ dashboard.content.news_published_30d }}</b>
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.content.kbPublished') }}</span><b>{{ dashboard.content.kb_articles_published_30d }}</b>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-card__title">
          {{ t('admin.analytics.activity.title') }}
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.activity.auditEvents') }}</span><b>{{ dashboard.activity.audit_events_24h }}</b>
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.activity.logins') }}</span><b>{{ dashboard.activity.logins_24h }}</b>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-card__title">
          {{ t('admin.analytics.feedback.title') }}
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.feedback.total') }}</span><b>{{ feedback?.total ?? 0 }}</b>
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.feedback.open') }}</span><b>{{ feedback?.open ?? 0 }}</b>
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.feedback.inProgress') }}</span><b>{{ feedback?.in_progress ?? 0 }}</b>
        </div>
        <div class="kpi-row">
          <span>{{ t('admin.analytics.feedback.avgResponse') }}</span><b>{{ avgResponse }}</b>
        </div>
      </div>
    </div>

    <div
      v-if="dashboard"
      class="series-grid"
    >
      <div
        v-for="s in seriesCards"
        :key="s.key"
        class="series-card"
      >
        <div class="series-card__title">
          {{ s.title }}
        </div>
        <div
          class="sparkline"
          role="img"
          :aria-label="s.title"
        >
          <div
            v-for="(p, i) in s.data"
            :key="`${s.key}-${i}`"
            class="sparkline__bar"
            :style="{ height: sparkHeight(p.count, s.data) }"
            :title="`${p.day}: ${p.count}`"
            :aria-label="`${p.day}: ${p.count}`"
          />
        </div>
      </div>
    </div>

    <div
      v-if="selectedResource"
      class="series-grid"
    >
      <div class="series-card">
        <div class="series-card__header">
          <div class="series-card__title">
            {{ t('admin.analytics.drilldown.title', { name: selectedResource.title }) }}
          </div>
          <n-button
            text
            size="tiny"
            @click="selectedResource = null"
          >
            {{ t('common.close') }}
          </n-button>
        </div>
        <div
          v-if="resourceTrend.length"
          class="sparkline"
          role="img"
          :aria-label="t('admin.analytics.drilldown.title', { name: selectedResource.title })"
        >
          <div
            v-for="(p, i) in resourceTrend"
            :key="`rt-${i}`"
            class="sparkline__bar"
            :style="{ height: sparkHeight(p.count, resourceTrend) }"
            :title="`${p.day}: ${p.count}`"
            :aria-label="`${p.day}: ${p.count}`"
          />
        </div>
        <div
          v-else
          class="drilldown-empty"
        >
          {{ t('admin.analytics.drilldown.empty') }}
        </div>
      </div>
    </div>

    <div class="analytics-tables">
      <div class="series-card">
        <div class="series-card__header">
          <div class="series-card__title">
            {{ t('admin.analytics.topArticles.title') }}
          </div>
          <n-dropdown
            trigger="click"
            :options="exportOptions"
            @select="(k) => downloadExport('top-articles', k)"
          >
            <n-button
              text
              size="tiny"
              :title="t('admin.analytics.export')"
            >
              <template #icon>
                <n-icon><DownloadOutline /></n-icon>
              </template>
            </n-button>
          </n-dropdown>
        </div>
        <n-data-table
          :columns="topArticlesColumns"
          :data="topArticles"
          :loading="loadingTopArticles"
          :pagination="false"
          :max-height="320"
          size="small"
        />
      </div>
      <div class="series-card">
        <div class="series-card__header">
          <div class="series-card__title">
            {{ t('admin.analytics.topNews.title') }}
          </div>
          <n-dropdown
            trigger="click"
            :options="exportOptions"
            @select="(k) => downloadExport('top-news', k)"
          >
            <n-button
              text
              size="tiny"
              :title="t('admin.analytics.export')"
            >
              <template #icon>
                <n-icon><DownloadOutline /></n-icon>
              </template>
            </n-button>
          </n-dropdown>
        </div>
        <n-data-table
          :columns="topNewsColumns"
          :data="topNews"
          :loading="loadingTopNews"
          :pagination="false"
          :max-height="320"
          size="small"
        />
      </div>
      <div class="series-card">
        <div class="series-card__header">
          <div class="series-card__title">
            {{ t('admin.analytics.topFiles.title') }}
          </div>
          <n-dropdown
            trigger="click"
            :options="exportOptions"
            @select="(k) => downloadExport('top-files', k)"
          >
            <n-button
              text
              size="tiny"
              :title="t('admin.analytics.export')"
            >
              <template #icon>
                <n-icon><DownloadOutline /></n-icon>
              </template>
            </n-button>
          </n-dropdown>
        </div>
        <n-data-table
          :columns="topFilesColumns"
          :data="topFiles"
          :loading="loadingTopFiles"
          :pagination="false"
          :max-height="320"
          size="small"
          :row-props="fileRowProps"
        />
      </div>
      <div class="series-card">
        <div class="series-card__header">
          <div class="series-card__title">
            {{ t('admin.analytics.topLinks.title') }}
          </div>
          <n-dropdown
            trigger="click"
            :options="exportOptions"
            @select="(k) => downloadExport('top-links', k)"
          >
            <n-button
              text
              size="tiny"
              :title="t('admin.analytics.export')"
            >
              <template #icon>
                <n-icon><DownloadOutline /></n-icon>
              </template>
            </n-button>
          </n-dropdown>
        </div>
        <n-data-table
          :columns="topLinksColumns"
          :data="topLinks"
          :loading="loadingTopLinks"
          :pagination="false"
          :max-height="320"
          size="small"
          :row-props="linkRowProps"
        />
      </div>
      <div class="series-card">
        <div class="series-card__header">
          <div class="series-card__title">
            {{ t('admin.analytics.staleContent.title') }}
          </div>
          <n-dropdown
            trigger="click"
            :options="exportOptions"
            @select="(k) => downloadExport('stale-content', k)"
          >
            <n-button
              text
              size="tiny"
              :title="t('admin.analytics.export')"
            >
              <template #icon>
                <n-icon><DownloadOutline /></n-icon>
              </template>
            </n-button>
          </n-dropdown>
        </div>
        <n-data-table
          :columns="staleColumns"
          :data="staleContent"
          :loading="loadingStale"
          :pagination="false"
          :max-height="320"
          size="small"
        />
      </div>
      <div class="series-card">
        <div class="series-card__header">
          <div class="series-card__title">
            {{ t('admin.analytics.departments.title') }}
          </div>
          <n-dropdown
            trigger="click"
            :options="exportOptions"
            @select="(k) => downloadExport('departments', k)"
          >
            <n-button
              text
              size="tiny"
              :title="t('admin.analytics.export')"
            >
              <template #icon>
                <n-icon><DownloadOutline /></n-icon>
              </template>
            </n-button>
          </n-dropdown>
        </div>
        <n-data-table
          :columns="departmentsColumns"
          :data="departments"
          :loading="loadingDepartments"
          :pagination="false"
          :max-height="320"
          size="small"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDataTable, NDropdown, NIcon, NSelect, type DataTableColumns } from 'naive-ui'
import { SyncOutline, DownloadOutline } from '@vicons/ionicons5'
import {
  analyticsExportUrl,
  type ExportDataset,
  type TopArticle, type TopNews, type TopFile, type TopLink,
  type DepartmentRow, type StaleContentItem,
} from '../../../api/analytics'
import {
  useAnalyticsDashboardQuery, useAnalyticsTopArticlesQuery,
  useAnalyticsTopNewsQuery, useAnalyticsTopFilesQuery, useAnalyticsTopLinksQuery,
  useAnalyticsDepartmentsQuery, useAnalyticsStaleContentQuery, useAnalyticsFeedbackQuery,
  useAnalyticsResourceTrendQuery,
} from '../../../queries/admin'
import { useQueryClient } from '@tanstack/vue-query'

const { t } = useI18n()
const qc = useQueryClient()

const period = ref<number>(30)
const periodOptions = computed(() => [
  { label: t('admin.analytics.period.d7'), value: 7 },
  { label: t('admin.analytics.period.d30'), value: 30 },
  { label: t('admin.analytics.period.d90'), value: 90 },
  { label: t('admin.analytics.period.d365'), value: 365 },
])

const exportOptions = [
  { label: 'CSV', key: 'csv' },
  { label: 'XLSX', key: 'xlsx' },
]

const { data: dashboardData, isLoading: loadingDashboard } = useAnalyticsDashboardQuery(period)
const { data: topArticlesData, isLoading: loadingTopArticles } = useAnalyticsTopArticlesQuery(period)
const { data: topNewsData, isLoading: loadingTopNews } = useAnalyticsTopNewsQuery(period)
const { data: topFilesData, isLoading: loadingTopFiles } = useAnalyticsTopFilesQuery(period)
const { data: topLinksData, isLoading: loadingTopLinks } = useAnalyticsTopLinksQuery(period)
const { data: departmentsData, isLoading: loadingDepartments } = useAnalyticsDepartmentsQuery(period)
const { data: staleData, isLoading: loadingStale } = useAnalyticsStaleContentQuery(period)
const { data: feedbackData } = useAnalyticsFeedbackQuery(period)

const selectedResource = ref<{ kind: 'link' | 'file'; id: string; title: string } | null>(null)
const selectedKind = computed<'link' | 'file'>(() => selectedResource.value?.kind ?? 'link')
const selectedId = computed<string | null>(() => selectedResource.value?.id ?? null)
const { data: resourceTrendData } = useAnalyticsResourceTrendQuery(selectedKind, selectedId, period)

const dashboard = computed(() => dashboardData.value ?? null)
const topArticles = computed(() => topArticlesData.value ?? [])
const topNews = computed(() => topNewsData.value ?? [])
const topFiles = computed(() => topFilesData.value ?? [])
const topLinks = computed(() => topLinksData.value ?? [])
const departments = computed(() => departmentsData.value ?? [])
const staleContent = computed(() => staleData.value ?? [])
const feedback = computed(() => feedbackData.value ?? null)
const resourceTrend = computed(() => resourceTrendData.value ?? [])

const seriesCards = computed(() => {
  const d = dashboard.value
  if (!d) return []
  return [
    { key: 'logins', title: t('admin.analytics.series.loginsTitle'), data: d.series.daily_logins_14d },
    { key: 'active', title: t('admin.analytics.series.activeUsersTitle'), data: d.series.daily_active_users },
    { key: 'publications', title: t('admin.analytics.series.publicationsTitle'), data: d.series.daily_publications_14d },
    { key: 'uploads', title: t('admin.analytics.series.uploadsTitle'), data: d.series.daily_uploads },
  ]
})

const avgResponse = computed(() => {
  const s = feedback.value?.avg_first_response_seconds
  if (s == null) return '—'
  const hours = s / 3600
  if (hours < 1) return `${Math.round(s / 60)} ${t('admin.analytics.feedback.minutes')}`
  if (hours < 48) return `${hours.toFixed(1)} ${t('admin.analytics.feedback.hours')}`
  return `${(hours / 24).toFixed(1)} ${t('admin.analytics.feedback.days')}`
})

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return ''
  try { return new Date(iso).toLocaleString() } catch { return iso }
}

function sparkHeight(value: number, series: { count: number }[]): string {
  if (!series || series.length === 0) return '2%'
  const max = Math.max(1, ...series.map((p) => p.count || 0))
  const pct = Math.round((value / max) * 100)
  return `${Math.max(2, pct)}%`
}

function downloadExport(dataset: ExportDataset, format: string | number) {
  const fmt = format === 'xlsx' ? 'xlsx' : 'csv'
  const url = analyticsExportUrl(dataset, fmt, period.value, 100)
  const a = document.createElement('a')
  a.href = url
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}

const linkRowProps = (row: TopLink) => ({
  style: 'cursor: pointer;',
  onClick: () => {
    selectedResource.value = { kind: 'link', id: row.resource_id, title: row.title || row.resource_id }
  },
})

const fileRowProps = (row: TopFile) => ({
  style: 'cursor: pointer;',
  onClick: () => {
    selectedResource.value = { kind: 'file', id: row.resource_id, title: row.title || row.resource_id }
  },
})

const topArticlesColumns = computed<DataTableColumns<TopArticle>>(() => [
  { title: t('admin.audit.columns.createdAt'), key: 'updated_at', width: 130, render: (r) => formatDateTime(r.updated_at) },
  { title: t('admin.analytics.topArticles.section'), key: 'section_title', minWidth: 120, ellipsis: { tooltip: true } },
  { title: t('admin.analytics.itemTitle'), key: 'title', minWidth: 160, ellipsis: { tooltip: true } },
  { title: t('admin.analytics.topArticles.viewCount'), key: 'view_count', width: 90, align: 'right' },
])

const topNewsColumns = computed<DataTableColumns<TopNews>>(() => [
  { title: t('admin.analytics.itemTitle'), key: 'title', minWidth: 200, ellipsis: { tooltip: true } },
  { title: t('admin.audit.columns.createdAt'), key: 'published_at', width: 150, render: (r) => formatDateTime(r.published_at) },
  { title: t('admin.analytics.topNews.viewCount'), key: 'view_count', width: 90, align: 'right' },
])

const topFilesColumns = computed<DataTableColumns<TopFile>>(() => [
  { title: t('admin.analytics.itemTitle'), key: 'title', minWidth: 200, ellipsis: { tooltip: true } },
  { title: t('admin.analytics.topFiles.lastDownload'), key: 'last_download', width: 150, render: (r) => formatDateTime(r.last_download) },
  { title: t('admin.analytics.topFiles.downloads'), key: 'downloads', width: 90, align: 'right' },
])

const topLinksColumns = computed<DataTableColumns<TopLink>>(() => [
  { title: t('admin.analytics.itemTitle'), key: 'title', minWidth: 180, ellipsis: { tooltip: true } },
  { title: t('admin.analytics.topLinks.clicks'), key: 'clicks', width: 90, align: 'right' },
  { title: t('admin.analytics.topLinks.uniqueUsers'), key: 'unique_users', width: 110, align: 'right' },
  { title: t('admin.analytics.topLinks.lastClick'), key: 'last_click', width: 150, render: (r) => formatDateTime(r.last_click) },
])

const staleColumns = computed<DataTableColumns<StaleContentItem>>(() => [
  { title: t('admin.analytics.staleContent.kind'), key: 'kind', width: 80, render: (r) => t(`admin.analytics.staleContent.kind_${r.kind}`) },
  { title: t('admin.analytics.itemTitle'), key: 'title', minWidth: 180, ellipsis: { tooltip: true } },
  { title: t('admin.analytics.staleContent.views'), key: 'view_count', width: 90, align: 'right' },
  { title: t('admin.analytics.staleContent.updatedAt'), key: 'updated_at', width: 130, render: (r) => formatDateTime(r.updated_at) },
])

const departmentsColumns = computed<DataTableColumns<DepartmentRow>>(() => [
  { title: t('admin.analytics.departments.department'), key: 'department', minWidth: 140, ellipsis: { tooltip: true }, render: (r) => r.department || '—' },
  { title: t('admin.analytics.departments.totalUsers'), key: 'total_users', width: 100, align: 'right' },
  { title: t('admin.analytics.departments.activeUsers'), key: 'active_users', width: 100, align: 'right' },
  { title: t('admin.analytics.departments.events'), key: 'events', width: 90, align: 'right' },
])

function loadAnalytics() {
  qc.invalidateQueries({ queryKey: ['admin', 'analytics'] })
}
</script>

<style scoped>
@import '../admin-tabs.css';

.analytics-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.analytics-period {
  width: 160px;
}

.series-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.series-card__header .series-card__title {
  margin-bottom: 0;
}

.drilldown-empty {
  font-size: 13px;
  color: var(--color-text-muted);
  padding: 24px 0;
  text-align: center;
}
</style>
