import { defineStore } from 'pinia'
import { ref, computed, onScopeDispose } from 'vue'
import { fetchMe, type UserMe } from '../api/auth'
import { fetchBootstrap } from '../api/bootstrap'
import { api, refreshAuth } from '../api/index'

export type LoadUserResult = 'ok' | 'unauthenticated' | 'network_error'

// Silently refresh the Keycloak access token every 4 minutes.
// Keycloak default Access Token Lifespan is 5 min — refreshing at 4 min
// leaves a comfortable safety margin even if the request is slow.
// The retry-on-401 in api/index.ts is the safety net if the timer misses
// (e.g. tab was suspended / laptop went to sleep).
const SILENT_REFRESH_INTERVAL_MS = 4 * 60 * 1000

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserMe | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const backendDown = ref(false)

  const isAuthenticated = computed(() => user.value !== null)
  const isEditor = computed(() => user.value?.role === 'editor' || user.value?.role === 'admin')
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isLocalUser = computed(() => user.value?.auth_source === 'local')

  let refreshTimer: ReturnType<typeof setInterval> | null = null

  function startSilentRefresh(): void {
    if (typeof window === 'undefined') return
    stopSilentRefresh()
    refreshTimer = setInterval(() => {
      // Errors are swallowed: if refresh fails, the next user-initiated
      // request will get a 401 and the retry-on-401 path will handle it
      // (or redirect to /login if refresh truly cannot succeed).
      void refreshAuth()
    }, SILENT_REFRESH_INTERVAL_MS)
  }

  function stopSilentRefresh(): void {
    if (refreshTimer !== null) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
  }

  async function loadUser(): Promise<LoadUserResult> {
    loading.value = true
    error.value = null
    backendDown.value = false
    try {
      user.value = await fetchMe()
      clearSSOState()
      startSilentRefresh()
      return 'ok'
    } catch (err: unknown) {
      user.value = null
      stopSilentRefresh()
      const status = (err as { status?: number; statusCode?: number })?.status
        ?? (err as { status?: number; statusCode?: number })?.statusCode
      if (status === 401) {
        return 'unauthenticated'
      }
      backendDown.value = true
      return 'network_error'
    } finally {
      loading.value = false
    }
  }

  async function loadBootstrap(): Promise<LoadUserResult> {
    loading.value = true
    error.value = null
    backendDown.value = false
    try {
      const data = await fetchBootstrap()
      user.value = data.user

      const { useBrandingStore } = await import('./branding')
      const { useModulesStore } = await import('./modules')
      const { useNotificationsStore } = await import('./notifications')

      useBrandingStore().setSettings(data.branding)
      const modulesStore = useModulesStore()
      modulesStore.setData(data.modules)
      modulesStore.setGalleryLinks(data.gallery_links)
      useNotificationsStore().setUnreadCount(data.unread_count)

      clearSSOState()
      startSilentRefresh()
      return 'ok'
    } catch (err: unknown) {
      user.value = null
      stopSilentRefresh()
      const status = (err as { status?: number; statusCode?: number })?.status
        ?? (err as { status?: number; statusCode?: number })?.statusCode
      if (status === 401) {
        return 'unauthenticated'
      }
      backendDown.value = true
      return 'network_error'
    } finally {
      loading.value = false
    }
  }

  // Loop-protection: счётчик попыток в sessionStorage с окном 30s.
  // Если за 30s было ≥2 редиректов на /api/v1/auth/login — не редиректим
  // ещё раз, а отправляем пользователя на страницу /auth/error.
  const SSO_ATTEMPTS_KEY = 'sso_attempts'
  const SSO_FAILED_KEY = 'sso_failed'
  const SSO_LOOP_WINDOW_MS = 30_000
  const SSO_LOOP_LIMIT = 2

  function _readAttempts(): number[] {
    if (typeof window === 'undefined') return []
    try {
      const raw = window.sessionStorage.getItem(SSO_ATTEMPTS_KEY)
      if (!raw) return []
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed.filter((n) => typeof n === 'number') : []
    } catch {
      return []
    }
  }

  function _writeAttempts(values: number[]): void {
    if (typeof window === 'undefined') return
    try {
      window.sessionStorage.setItem(SSO_ATTEMPTS_KEY, JSON.stringify(values))
    } catch {
      /* ignore */
    }
  }

  function clearSSOState(): void {
    if (typeof window === 'undefined') return
    try {
      window.sessionStorage.removeItem(SSO_ATTEMPTS_KEY)
      window.sessionStorage.removeItem(SSO_FAILED_KEY)
    } catch {
      /* ignore */
    }
  }

  function markSSOFailed(reason: string): void {
    if (typeof window === 'undefined') return
    try {
      window.sessionStorage.setItem(SSO_FAILED_KEY, reason)
    } catch {
      /* ignore */
    }
  }

  function _safeRedirectParam(value: string): string {
    return value && value !== '/' && /^\/(?![/\\])[^#]*$/.test(value)
      ? `?redirect=${encodeURIComponent(value)}`
      : ''
  }

  function redirectToSSO(redirectAfter = window.location.pathname + window.location.search): void {
    if (typeof window === 'undefined') return
    const now = Date.now()
    const recent = _readAttempts().filter((ts) => now - ts < SSO_LOOP_WINDOW_MS)
    if (recent.length >= SSO_LOOP_LIMIT) {
      markSSOFailed('loop_detected')
      const params = _safeRedirectParam(redirectAfter)
      window.location.href = `/auth/error?reason=loop_detected${params ? '&' + params.slice(1) : ''}`
      return
    }
    recent.push(now)
    _writeAttempts(recent)
    const params = _safeRedirectParam(redirectAfter)
    window.location.href = `/api/v1/auth/login${params}`
  }

  function logout(): void {
    user.value = null
    stopSilentRefresh()
    api('/auth/logout', { method: 'POST' }).finally(() => {
      // Backend ответит 302 на /auth/error?reason=logged_out (Keycloak)
      // или /auth/local?logged_out=1 (local). Браузер сам последует за редиректом
      // потому что fetch с credentials прозрачно его обрабатывает (manual mode не используем).
      // Однако ofetch получит финальный ответ и не выполнит навигацию. Поэтому
      // вручную отправляем пользователя на страницу выхода в зависимости от auth_source —
      // но user уже null, поэтому просто отправляем на /auth/error?reason=logged_out.
      window.location.href = '/auth/error?reason=logged_out'
    })
  }

  function onSessionExpired(): void {
    user.value = null
    stopSilentRefresh()
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('auth:expired', onSessionExpired)
    onScopeDispose(() => {
      window.removeEventListener('auth:expired', onSessionExpired)
      stopSilentRefresh()
    })
  }

  return {
    user, loading, error, backendDown,
    isAuthenticated, isEditor, isAdmin, isLocalUser,
    loadUser, loadBootstrap, redirectToSSO, clearSSOState, markSSOFailed, logout,
  }
})
