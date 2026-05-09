<template>
  <div class="analytics-wrap">
    <div class="tab-toolbar">
      <div class="analytics-meta">
        <span v-if="dashboard">{{ t('admin.analytics.generatedAt', { t: formatDateTime(dashboard.generated_at) }) }}</span>
      </div>
      <n-button :loading="loadingDashboard" @click="loadAnalytics">
        <template #icon><n-icon><SyncOutline /></n-icon></template>
        {{ t('admin.analytics.refresh') }}
      </n-button>
    </div>

    <div v-if="dashboard" class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-card__title">{{ t('admin.analytics.users.title') }}</div>
        <div class="kpi-row"><span>{{ t('admin.analytics.users.total') }}</span><b>{{ dashboard.users.total }}</b></div>
        <div class="kpi-row"><span>{{ t('admin.analytics.users.active30d') }}</span><b>{{ dashboard.users.active_30d }}</b></div>
        <div class="kpi-row"><span>{{ t('admin.analytics.users.active1h') }}</span><b>{{ dashboard.users.active_1h }}</b></div>
        <div class="kpi-row"><span>{{ t('admin.analytics.users.new30d') }}</span><b>{{ dashboard.users.new_30d }}</b></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-card__title">{{ t('admin.analytics.content.title') }}</div>
        <div class="kpi-row"><span>{{ t('admin.analytics.content.newsPublished') }}</span><b>{{ dashboard.content.news_published_30d }}</b></div>
        <div class="kpi-row"><span>{{ t('admin.analytics.content.kbPublished') }}</span><b>{{ dashboard.content.kb_articles_published_30d }}</b></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-card__title">{{ t('admin.analytics.activity.title') }}</div>
        <div class="kpi-row"><span>{{ t('admin.analytics.activity.auditEvents') }}</span><b>{{ dashboard.activity.audit_events_24h }}</b></div>
        <div class="kpi-row"><span>{{ t('admin.analytics.activity.logins') }}</span><b>{{ dashboard.activity.logins_24h }}</b></div>
      </div>
    </div>

    <div v-if="dashboard" class="series-grid">
      <div class="series-card">
        <div class="series-card__title">{{ t('admin.analytics.series.loginsTitle') }}</div>
        <div class="sparkline" role="img" :aria-label="t('admin.analytics.series.loginsTitle')">
          <div
            v-for="(p, i) in dashboard.series.daily_logins_14d"
            :key="`l-${i}`"
            class="sparkline__bar"
            :style="{ height: sparkHeight(p.count, dashboard.series.daily_logins_14d) }"
            :title="`${p.day}: ${p.count}`"
            :aria-label="`${p.day}: ${p.count}`"
          />
        </div>
      </div>
      <div class="series-card">
        <div class="series-card__title">{{ t('admin.analytics.series.publicationsTitle') }}</div>
        <div class="sparkline" role="img" :aria-label="t('admin.analytics.series.publicationsTitle')">
          <div
            v-for="(p, i) in dashboard.series.daily_publications_14d"
            :key="`p-${i}`"
            class="sparkline__bar"
            :style="{ height: sparkHeight(p.count, dashboard.series.daily_publications_14d) }"
            :title="`${p.day}: ${p.count}`"
            :aria-label="`${p.day}: ${p.count}`"
          />
        </div>
      </div>
    </div>

    <div class="analytics-tables">
      <div class="series-card">
        <div class="series-card__title">{{ t('admin.analytics.topArticles.title') }}</div>
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
        <div class="series-card__title">{{ t('admin.analytics.topNews.title') }}</div>
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
        <div class="series-card__title">{{ t('admin.analytics.topFiles.title') }}</div>
        <n-data-table
          :columns="topFilesColumns"
          :data="topFiles"
          :loading="loadingTopFiles"
          :pagination="false"
          :max-height="320"
          size="small"
        />
      </div>
      <div class="series-card">
        <div class="series-card__title">{{ t('admin.analytics.departments.title') }}</div>
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
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDataTable, NIcon, type DataTableColumns } from 'naive-ui'
import { SyncOutline } from '@vicons/ionicons5'
import { type TopArticle, type TopNews, type TopFile, type DepartmentRow } from '../../../api/analytics'
import {
  useAnalyticsDashboardQuery, useAnalyticsTopArticlesQuery,
  useAnalyticsTopNewsQuery, useAnalyticsTopFilesQuery, useAnalyticsDepartmentsQuery,
} from '../../../queries/admin'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../../queries/keys'

const { t } = useI18n()
const qc = useQueryClient()

const { data: dashboardData, isLoading: loadingDashboard } = useAnalyticsDashboardQuery()
const { data: topArticlesData, isLoading: loadingTopArticles } = useAnalyticsTopArticlesQuery()
const { data: topNewsData, isLoading: loadingTopNews } = useAnalyticsTopNewsQuery()
const { data: topFilesData, isLoading: loadingTopFiles } = useAnalyticsTopFilesQuery()
const { data: departmentsData, isLoading: loadingDepartments } = useAnalyticsDepartmentsQuery()

const dashboard = computed(() => dashboardData.value ?? null)
const topArticles = computed(() => topArticlesData.value ?? [])
const topNews = computed(() => topNewsData.value ?? [])
const topFiles = computed(() => topFilesData.value ?? [])
const departments = computed(() => departmentsData.value ?? [])

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

const topArticlesColumns = computed<DataTableColumns<TopArticle>>(() => [
  { title: t('admin.audit.columns.createdAt'), key: 'updated_at', width: 130, render: (r) => formatDateTime(r.updated_at) },
  { title: t('admin.analytics.topArticles.section'), key: 'section_title', ellipsis: { tooltip: true } },
  { title: t('admin.analytics.itemTitle'), key: 'title', ellipsis: { tooltip: true } },
  { title: t('admin.analytics.topArticles.viewCount'), key: 'view_count', width: 110, align: 'right' },
])

const topNewsColumns = computed<DataTableColumns<TopNews>>(() => [
  { title: t('admin.analytics.itemTitle'), key: 'title', ellipsis: { tooltip: true } },
  { title: t('admin.audit.columns.createdAt'), key: 'published_at', width: 150, render: (r) => formatDateTime(r.published_at) },
  { title: t('admin.analytics.topNews.viewCount'), key: 'view_count', width: 110, align: 'right' },
])

const topFilesColumns = computed<DataTableColumns<TopFile>>(() => [
  { title: t('admin.analytics.resource'), key: 'resource_id', ellipsis: { tooltip: true } },
  { title: t('admin.analytics.itemTitle'), key: 'title', ellipsis: { tooltip: true } },
  { title: t('admin.analytics.topFiles.lastDownload'), key: 'last_download', width: 150, render: (r) => formatDateTime(r.last_download) },
  { title: t('admin.analytics.topFiles.downloads'), key: 'downloads', width: 110, align: 'right' },
])

const departmentsColumns = computed<DataTableColumns<DepartmentRow>>(() => [
  { title: t('admin.analytics.departments.department'), key: 'department', ellipsis: { tooltip: true } },
  { title: t('admin.analytics.departments.totalUsers'), key: 'total_users', width: 110, align: 'right' },
  { title: t('admin.analytics.departments.activeUsers'), key: 'active_users', width: 110, align: 'right' },
  { title: t('admin.analytics.departments.events'), key: 'events', width: 110, align: 'right' },
])

function loadAnalytics() {
  qc.invalidateQueries({ queryKey: ['admin', 'analytics'] })
}
</script>

<style scoped>
@import '../admin-tabs.css';
</style>
