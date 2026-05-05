import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchMe, type UserMe } from '../api/auth'
import { api } from '../api/index'

export type LoadUserResult = 'ok' | 'unauthenticated' | 'network_error'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserMe | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const backendDown = ref(false)

  const isAuthenticated = computed(() => user.value !== null)
  const isEditor = computed(() => user.value?.role === 'editor' || user.value?.role === 'admin')
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isLocalUser = computed(() => user.value?.auth_source === 'local')

  async function loadUser(): Promise<LoadUserResult> {
    loading.value = true
    error.value = null
    backendDown.value = false
    try {
      user.value = await fetchMe()
      return 'ok'
    } catch (err: unknown) {
      user.value = null
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

  function redirectToLogin(redirectAfter = window.location.pathname): void {
    const safe = redirectAfter && redirectAfter !== '/' && /^\/[^#]*$/.test(redirectAfter)
    const params = safe ? `?redirect=${encodeURIComponent(redirectAfter)}` : ''
    window.location.href = `/login${params}`
  }

  function logout(): void {
    user.value = null
    api('/auth/logout', { method: 'POST' }).finally(() => {
      window.location.href = '/login'
    })
  }

  function onSessionExpired(): void {
    user.value = null
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('auth:expired', onSessionExpired)
  }

  return { user, loading, error, backendDown, isAuthenticated, isEditor, isAdmin, isLocalUser, loadUser, redirectToLogin, logout }
})
