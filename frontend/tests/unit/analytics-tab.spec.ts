/**
 * AnalyticsTab: карточка «Согласование 1С» (approvals-блок дашборда) +
 * ширина обёртки AdminPage (analytics → u-page-wrap--full).
 *
 * Покрывает новые строки AnalyticsTab.vue (kpi-rows, двухцветный sparkline,
 * легенда) и ветку wrapVariant в AdminPage.vue — diff-coverage гейт.
 */
import { ref } from 'vue'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const routeQuery: { tab: string | null } = { tab: null }

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { tab: routeQuery.tab } }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('naive-ui', () => ({
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'size'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NButton: { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ['size', 'text', 'loading', 'title'] },
  NDataTable: { template: '<div class="n-data-table" />', props: ['data', 'columns', 'loading', 'pagination'] },
  NDropdown: { template: '<div class="n-dropdown"><slot name="trigger" /></div>', props: ['trigger', 'options'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  NSelect: { template: '<select />', props: ['value', 'options', 'size'] },
  useMessage: () => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  SyncOutline: { template: '<span />' },
  DownloadOutline: { template: '<span />' },
}))

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('../../src/stores/modules', () => ({
  useModulesStore: () => ({ isEnabled: () => true }),
}))

const dashboardFixture: DashboardOut = {
  generated_at: '2026-09-07T09:00:00Z',
  users: { total: 10, active_30d: 8, active_1h: 2, new_30d: 1 },
  content: { news_published_30d: 3, kb_articles_published_30d: 5 },
  activity: { audit_events_24h: 100, logins_24h: 20, wau_7d: 7, mau_30d: 9 },
  series: {
    daily_logins_14d: [{ day: '2026-09-06', count: 4 }],
    daily_publications_14d: [],
    daily_active_users: [],
    daily_uploads: [],
  },
  approvals: {
    approved: 12,
    rejected: 3,
    active_users: 4,
    last_event_at: '2026-09-06T15:12:00Z',
    daily: [
      { day: '2026-09-04', approved: 5, rejected: 1 },
      { day: '2026-09-05', approved: 7, rejected: 2 },
    ],
  },
}

vi.mock('../../src/queries/admin', () => ({
  useAnalyticsDashboardQuery: () => ({ data: ref(dashboardFixture), isLoading: ref(false) }),
  useAnalyticsTopArticlesQuery: () => ({ data: ref([]), isLoading: ref(false) }),
  useAnalyticsTopNewsQuery: () => ({ data: ref([]), isLoading: ref(false) }),
  useAnalyticsTopFilesQuery: () => ({ data: ref([]), isLoading: ref(false) }),
  useAnalyticsTopLinksQuery: () => ({ data: ref([]), isLoading: ref(false) }),
  useAnalyticsDepartmentsQuery: () => ({ data: ref([]), isLoading: ref(false) }),
  useAnalyticsStaleContentQuery: () => ({ data: ref([]), isLoading: ref(false) }),
  useAnalyticsFeedbackQuery: () => ({ data: ref(null), isLoading: ref(false) }),
  useAnalyticsResourceTrendQuery: () => ({ data: ref([]) }),
}))

vi.mock('../../src/api/analytics', () => ({
  analyticsExportUrl: vi.fn(() => '#'),
}))

import AnalyticsTab from '../../src/pages/admin/tabs/AnalyticsTab.vue'
import AdminPage from '../../src/pages/AdminPage.vue'
import type { DashboardOut } from '../../src/api/analytics'

const globalPlugins = { plugins: [], stubs: {} }

describe('AnalyticsTab: карточка «Согласование 1С»', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('монтируется с фикстурой дашборда', () => {
    const w = mount(AnalyticsTab, { global: globalPlugins })
    expect(w.exists()).toBe(true)
  })

  it('показывает итоги согласований за период', () => {
    const w = mount(AnalyticsTab, { global: globalPlugins })
    const text = w.text()
    expect(text).toContain('admin.analytics.approvals.title')
    // approved=12, rejected=3, active_users=4 — из фикстуры
    expect(text).toContain('12')
    expect(text).toContain('3')
    expect(text).toContain('4')
    // Пятая карточка сетки — approvals; последнее событие отформатировано
    // (валидная дата из фикстуры, не заглушка «—»).
    const approvalsCard = w.findAll('.series-card')[4]
    expect(approvalsCard.text()).toContain('2026')
  })

  it('рисует двухцветный ряд по дням и легенду', () => {
    const w = mount(AnalyticsTab, { global: globalPlugins })
    expect(w.findAll('.sparkline__pair')).toHaveLength(2)
    expect(w.findAll('.sparkline__bar--approved')).toHaveLength(2) // по бару на день
    expect(w.findAll('.sparkline__bar--rejected')).toHaveLength(2)
    expect(w.findAll('.spark-legend__item')).toHaveLength(2)
  })

  it('без событий показывает «—» и пустой ряд', () => {
    const saved = dashboardFixture.approvals
    dashboardFixture.approvals = {
      approved: 0,
      rejected: 0,
      active_users: 0,
      last_event_at: null,
      daily: [],
    }
    try {
      const w = mount(AnalyticsTab, { global: globalPlugins })
      const approvalsCard = w.findAll('.series-card')[4]
      expect(approvalsCard.text()).toContain('—')
      expect(w.findAll('.sparkline__pair')).toHaveLength(0)
    } finally {
      dashboardFixture.approvals = saved
    }
  })
})

describe('AdminPage: ширина обёртки по вкладке', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('analytics → u-page-wrap--full', () => {
    routeQuery.tab = 'analytics'
    const w = mount(AdminPage, { shallow: true })
    expect(w.find('.admin-wrap').classes()).toContain('u-page-wrap--full')
  })

  it('остальные вкладки → u-page-wrap--wide (как раньше)', () => {
    routeQuery.tab = 'users'
    const w = mount(AdminPage, { shallow: true })
    expect(w.find('.admin-wrap').classes()).toContain('u-page-wrap--wide')
    expect(w.find('.admin-wrap').classes()).not.toContain('u-page-wrap--full')
    routeQuery.tab = null
  })
})
