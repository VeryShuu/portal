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

// При возврате к вкладке из фона токен мог истечь: браузеры замораживают/
// троттлят setInterval в фоновых вкладках (а при сне ноутбука он вообще не
// тикает), поэтому таймер silent-refresh пропускается. Чтобы не ловить 401 и
// не уходить в редирект-bounce через SSO, при `visibilitychange → visible`
// проактивно обновляем токен. Клиентский guard не дёргает refresh чаще, чем
// раз в минуту (бэкенд дополнительно коалесит близкие refresh в окне 10s).
const VISIBILITY_REFRESH_MIN_INTERVAL_MS = 60 * 1000

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
  // Момент последнего инициированного нами refresh — для guard'а в обработчике
  // видимости (не дёргать refresh при каждом мелком переключении вкладок).
  let lastRefreshAt = 0

  function _triggerRefresh(): void {
    // Errors are swallowed: if refresh fails, the next user-initiated
    // request will get a 401 and the retry-on-401 path will handle it
    // (or redirect to /login if refresh truly cannot succeed).
    lastRefreshAt = Date.now()
    void refreshAuth()
  }

  function startSilentRefresh(): void {
    if (typeof window === 'undefined') return
    stopSilentRefresh()
    // Токен только что подтверждён загрузкой — считаем его свежим, чтобы
    // обработчик видимости не сделал лишний refresh сразу после логина.
    lastRefreshAt = Date.now()
    refreshTimer = setInterval(_triggerRefresh, SILENT_REFRESH_INTERVAL_MS)
  }

  function stopSilentRefresh(): void {
    if (refreshTimer !== null) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
  }

  async function onVisibilityChange(): Promise<void> {
    if (typeof document === 'undefined') return
    if (document.visibilityState !== 'visible') return
    // Только для уже залогиненного пользователя: гость и так пойдёт обычным
    // SSO-путём через router-guard / retry-on-401.
    if (user.value === null) return
    if (Date.now() - lastRefreshAt < VISIBILITY_REFRESH_MIN_INTERVAL_MS) return
    lastRefreshAt = Date.now()
    const ok = await refreshAuth()
    if (!ok) {
      // Возврат из долгого фона: access-токен почти наверняка уже истёк, и если
      // refresh не прошёл — значит сама сессия (Keycloak refresh_token) мертва
      // (idle ≥ SSO Idle / max ≥ SSO Max / отозвана). Вместо немой переадресации
      // на SSO (которая при повторных bounce'ах добивает loop-guard и показывает
      // пугающее «Слишком много попыток входа») показываем спокойный экран
      // «Сессия истекла → Войти». Таймерный путь сюда НЕ ведём: там access ещё
      // жив ~15 мин, и транзиентный сбой refresh не должен выбивать пользователя.
      if (user.value !== null) redirectToSessionExpired()
      return
    }
    // Перевыставляем 4-минутную каденцию от текущего момента: фоновый таймер
    // мог быть заморожен и «сбиться».
    startSilentRefresh()
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

      // Dynamic imports break the cyclic dependency:
      //   auth → branding/modules/notifications → api/index → auth
      // Static imports would cause a circular reference that Vite/TypeScript resolves
      // unpredictably (the imported store may be undefined at module init time).
      // These three stores depend on api/index which re-exports refreshAuth from this store,
      // so they cannot be statically imported at the top of this file.
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

  // Грациозный re-login после истечения сессии (в отличие от loop_detected —
  // это не «сломанный цикл», а ожидаемое завершение долгого простоя). Не
  // дёргает loop-counter; показывает спокойный экран с кнопкой «Войти».
  function redirectToSessionExpired(
    redirectAfter = window.location.pathname + window.location.search,
  ): void {
    if (typeof window === 'undefined') return
    stopSilentRefresh()
    user.value = null
    if (window.location.pathname.startsWith('/auth/')) return
    markSSOFailed('session_expired')
    const params = _safeRedirectParam(redirectAfter)
    window.location.href = `/auth/error?reason=session_expired${params ? '&' + params.slice(1) : ''}`
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

  function setUser(updated: UserMe): void {
    user.value = updated
  }

  function onSessionExpired(): void {
    user.value = null
    stopSilentRefresh()
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('auth:expired', onSessionExpired)
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibilityChange)
    }
    onScopeDispose(() => {
      window.removeEventListener('auth:expired', onSessionExpired)
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibilityChange)
      }
      stopSilentRefresh()
    })
  }

  return {
    user, loading, error, backendDown,
    isAuthenticated, isEditor, isAdmin, isLocalUser,
    loadUser, loadBootstrap, redirectToSSO, redirectToSessionExpired,
    clearSSOState, markSSOFailed, logout, setUser,
  }
})
