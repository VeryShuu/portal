import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { fetchUsers, type UserPublic } from '../api/users'
import {
  fetchAuditEvents, fetchAuditEventTypes, fetchAuditQueueDepth,
  type AuditFilters,
} from '../api/audit'
import {
  fetchDashboard, fetchTopArticles, fetchTopNews, fetchTopFiles, fetchDepartments,
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

export function useAnalyticsDashboardQuery() {
  return useQuery({
    queryKey: queryKeys.admin.analyticsDashboard(),
    queryFn: () => fetchDashboard(),
    staleTime: 60_000,
  })
}

export function useAnalyticsTopArticlesQuery() {
  return useQuery({
    queryKey: queryKeys.admin.analyticsTopArticles(),
    queryFn: () => fetchTopArticles(30, 10),
    staleTime: 60_000,
  })
}

export function useAnalyticsTopNewsQuery() {
  return useQuery({
    queryKey: queryKeys.admin.analyticsTopNews(),
    queryFn: () => fetchTopNews(30, 10),
    staleTime: 60_000,
  })
}

export function useAnalyticsTopFilesQuery() {
  return useQuery({
    queryKey: queryKeys.admin.analyticsTopFiles(),
    queryFn: () => fetchTopFiles(30, 10),
    staleTime: 60_000,
  })
}

export function useAnalyticsDepartmentsQuery() {
  return useQuery({
    queryKey: queryKeys.admin.analyticsDepartments(),
    queryFn: () => fetchDepartments(30),
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
