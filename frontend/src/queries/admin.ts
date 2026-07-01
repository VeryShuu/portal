import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { fetchUsers, type UserPublic } from '../api/users'
import {
  fetchEmailOutbox, fetchEmailOutboxItem, retryEmailOutboxItem, cancelEmailOutboxItem,
  type EmailOutboxFilters,
} from '../api/emailOutbox'
import {
  fetchAuditEvents, fetchAuditEventTypes, fetchAuditQueueDepth,
  type AuditFilters,
} from '../api/audit'
import {
  fetchDashboard, fetchTopArticles, fetchTopNews, fetchTopFiles, fetchTopLinks, fetchDepartments,
  fetchStaleContent, fetchFeedbackStats, fetchResourceTrend,
} from '../api/analytics'
import {
  fetchAttributeMappings, discoverAttributes,
} from '../api/userAttributeMappings'
import { fetchLinks, type ServiceLink } from '../api/links'
import { api } from '../api'
import { queryKeys } from './keys'

export interface PaginatedUsers {
  items: UserPublic[]
  total: number
}

export interface AdminEmailSettings {
  host: string
  port: number
  from_address: string
  username: string
  password_set: boolean
  use_tls: boolean
  use_starttls: boolean
}

export interface AdminSystemSettings {
  portal_base_url: string
  nextcloud_url: string
  nc_user_id_field: string
  nc_service_app_password_set: boolean
  max_upload_size_mb: number
  allowed_cidr: string
  prometheus_metrics_enabled: boolean
  news_attachment_max_size_mb: number
  kb_media_max_size_mb: number
  kb_attachment_max_size_mb: number
  log_level: string
  timezone: string
  sentry_dsn_set: boolean
  log_force_json: boolean | null
  log_slow_request_ms: number
  arq_max_jobs: number
  photo_gallery_url: string
  photo_gallery_mode: string
  photo_gallery_new_tab: boolean
  video_gallery_url: string
  nc_service_username: string
  nc_files_root: string
  kb_import_max_size_mb: number
  kb_trash_retention_days: number
  metrics_token_set: boolean
  phone_extract_regex: string
  onboarding_enabled: boolean
  onboarding_reset_trigger: string
  onboarding_steps:
    | { id: string; selector: string; title: string; body: string; is_new?: boolean }[]
    | null
}

export interface AdminTlsStatus {
  cert_exists: boolean
  key_exists: boolean
  cert_expires_at: string | null
  cert_subject: string | null
}

export interface AdminKeycloakSettings {
  keycloak_url: string
  keycloak_realm: string
  oidc_client_id: string
  oidc_client_secret_set: boolean
  sync_client_id: string
  sync_client_secret_set: boolean
}

export interface AdminKeycloakSyncStatus {
  last_run_at: string | null
  last_count: number | null
  last_status: string | null
}

export interface PhotosModuleOut {
  enabled: boolean
  widget_limit: number
  max_size_mb: number
  allowed_mime: string[]
  strip_gps: boolean
}

export interface MeetingsModuleOut {
  enabled: boolean
  calendar_start_hour: number
  calendar_end_hour: number
  max_recurrence_horizon_days: number
  min_search_chars: number
}

export interface AdminModulesOut {
  nextcloud: { enabled: boolean }
  photos: PhotosModuleOut
  meetings: MeetingsModuleOut
  directories: { enabled: boolean }
  signature: { enabled: boolean }
  helpdesk: { enabled: boolean }
}

export function useAdminUsersQuery(params: MaybeRefOrGetter<{
  q?: string
  page?: number
  page_size?: number
}> = {}) {
  return useQuery({
    queryKey: computed(() => queryKeys.admin.users(toValue(params) as Record<string, unknown>)),
    queryFn: () => fetchUsers(toValue(params) ?? {}),
    staleTime: 0,
    placeholderData: (prev) => prev,
  })
}

export function useAuditEventTypesQuery() {
  return useQuery({
    queryKey: queryKeys.admin.auditEventTypes(),
    queryFn: fetchAuditEventTypes,
    staleTime: 300_000,
  })
}

export function useAuditQueueQuery() {
  return useQuery({
    queryKey: queryKeys.admin.auditQueue(),
    queryFn: fetchAuditQueueDepth,
    staleTime: 30_000,
  })
}

export function useAuditEventsQuery(params: MaybeRefOrGetter<AuditFilters>) {
  return useQuery({
    queryKey: computed(() => queryKeys.admin.audit(toValue(params) as Record<string, unknown>)),
    queryFn: () => fetchAuditEvents(toValue(params) ?? {}),
    staleTime: 0,
    placeholderData: (prev) => prev,
  })
}

export function useAnalyticsDashboardQuery(days: MaybeRefOrGetter<number> = 14) {
  return useQuery({
    queryKey: computed(() => queryKeys.admin.analyticsDashboard(toValue(days))),
    queryFn: () => fetchDashboard(toValue(days)),
    staleTime: 60_000,
  })
}

export function useAnalyticsTopArticlesQuery(days: MaybeRefOrGetter<number> = 30) {
  return useQuery({
    queryKey: computed(() => queryKeys.admin.analyticsTopArticles(toValue(days))),
    queryFn: () => fetchTopArticles(toValue(days), 10),
    staleTime: 60_000,
  })
}

export function useAnalyticsTopNewsQuery(days: MaybeRefOrGetter<number> = 30) {
  return useQuery({
    queryKey: computed(() => queryKeys.admin.analyticsTopNews(toValue(days))),
    queryFn: () => fetchTopNews(toValue(days), 10),
    staleTime: 60_000,
  })
}

export function useAnalyticsTopFilesQuery(days: MaybeRefOrGetter<number> = 30) {
  return useQuery({
    queryKey: computed(() => queryKeys.admin.analyticsTopFiles(toValue(days))),
    queryFn: () => fetchTopFiles(toValue(days), 10),
    staleTime: 60_000,
  })
}

export function useAnalyticsTopLinksQuery(days: MaybeRefOrGetter<number> = 30) {
  return useQuery({
    queryKey: computed(() => queryKeys.admin.analyticsTopLinks(toValue(days))),
    queryFn: () => fetchTopLinks(toValue(days), 10),
    staleTime: 60_000,
  })
}

export function useAnalyticsDepartmentsQuery(days: MaybeRefOrGetter<number> = 30) {
  return useQuery({
    queryKey: computed(() => queryKeys.admin.analyticsDepartments(toValue(days))),
    queryFn: () => fetchDepartments(toValue(days)),
    staleTime: 60_000,
  })
}

export function useAnalyticsStaleContentQuery(days: MaybeRefOrGetter<number> = 90) {
  return useQuery({
    queryKey: computed(() => queryKeys.admin.analyticsStaleContent(toValue(days))),
    queryFn: () => fetchStaleContent(toValue(days), 20),
    staleTime: 60_000,
  })
}

export function useAnalyticsFeedbackQuery(days: MaybeRefOrGetter<number> = 30) {
  return useQuery({
    queryKey: computed(() => queryKeys.admin.analyticsFeedback(toValue(days))),
    queryFn: () => fetchFeedbackStats(toValue(days)),
    staleTime: 60_000,
  })
}

export function useAnalyticsResourceTrendQuery(
  kind: MaybeRefOrGetter<'link' | 'file'>,
  resourceId: MaybeRefOrGetter<string | null>,
  days: MaybeRefOrGetter<number> = 30,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.admin.analyticsResourceTrend(toValue(kind), toValue(resourceId) ?? '', toValue(days)),
    ),
    queryFn: () => fetchResourceTrend(toValue(resourceId) as string, toValue(kind), toValue(days)),
    enabled: computed(() => !!toValue(resourceId)),
    staleTime: 60_000,
  })
}

export function useEmailSettingsQuery() {
  return useQuery({
    queryKey: queryKeys.admin.emailSettings(),
    queryFn: () => api<AdminEmailSettings>('/admin/email-settings'),
    staleTime: 60_000,
  })
}

export function useSystemSettingsQuery() {
  return useQuery({
    queryKey: queryKeys.admin.systemSettings(),
    queryFn: () => api<AdminSystemSettings>('/admin/system/settings'),
    staleTime: 60_000,
  })
}

export function useTlsStatusQuery() {
  return useQuery({
    queryKey: queryKeys.admin.tlsStatus(),
    queryFn: () => api<AdminTlsStatus>('/admin/system/tls/status'),
    staleTime: 60_000,
  })
}

export function useKeycloakSettingsQuery() {
  return useQuery({
    queryKey: queryKeys.admin.keycloakSettings(),
    queryFn: () => api<AdminKeycloakSettings>('/admin/keycloak/settings'),
    staleTime: 60_000,
  })
}

export function useKeycloakSyncStatusQuery() {
  return useQuery({
    queryKey: queryKeys.admin.keycloakSyncStatus(),
    queryFn: () => api<AdminKeycloakSyncStatus>('/admin/keycloak/sync/status'),
    staleTime: 30_000,
  })
}

export function useModulesAdminQuery() {
  return useQuery({
    queryKey: queryKeys.admin.modules(),
    queryFn: () => api<AdminModulesOut>('/admin/modules'),
    staleTime: 60_000,
  })
}

export function useUserAttributeMappingsQuery() {
  return useQuery({
    queryKey: queryKeys.admin.userAttributes(),
    queryFn: () => fetchAttributeMappings(),
    staleTime: 60_000,
  })
}

export function useDiscoverAttributesQuery() {
  return useQuery({
    queryKey: queryKeys.admin.discoverAttributes(),
    queryFn: () => discoverAttributes(),
    staleTime: 120_000,
  })
}

export function useAdminLinksQuery() {
  return useQuery({
    queryKey: queryKeys.admin.links(),
    queryFn: (): Promise<{ items: ServiceLink[] }> => fetchLinks({ include_inactive: true }),
    staleTime: 30_000,
  })
}

export function useInvalidateAdminLinks() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: queryKeys.admin.links() })
}

export function useEmailOutboxQuery(params: MaybeRefOrGetter<EmailOutboxFilters>) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.admin.emailOutbox(toValue(params) as Record<string, unknown>),
    ),
    queryFn: () => fetchEmailOutbox(toValue(params) ?? {}),
    staleTime: 0,
    placeholderData: (prev) => prev,
  })
}

export function useEmailOutboxItemQuery(id: MaybeRefOrGetter<string | null>) {
  return useQuery({
    queryKey: computed(() => queryKeys.admin.emailOutboxItem(String(toValue(id) ?? ''))),
    queryFn: () => fetchEmailOutboxItem(String(toValue(id))),
    enabled: computed(() => !!toValue(id)),
    staleTime: 0,
  })
}

export function useRetryEmailOutboxMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => retryEmailOutboxItem(id, true),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'email-outbox'] }),
  })
}

export function useCancelEmailOutboxMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => cancelEmailOutboxItem(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'email-outbox'] }),
  })
}
