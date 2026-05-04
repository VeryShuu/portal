import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchMe, type UserMe } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserMe | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => user.value !== null)
  const isEditor = computed(() => user.value?.role === 'editor' || user.value?.role === 'admin')
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isLocalUser = computed(() => user.value?.auth_source === 'local')

  async function loadUser(): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      user.value = await fetchMe()
      return true
    } catch {
      user.value = null
      return false
    } finally {
      loading.value = false
    }
  }

  function redirectToLogin(redirectAfter = window.location.pathname): void {
    const params = redirectAfter && redirectAfter !== '/' ? `?redirect=${encodeURIComponent(redirectAfter)}` : ''
    window.location.href = `/login${params}`
  }

  function logout(): void {
    user.value = null
    const form = document.createElement('form')
    form.method = 'POST'
    form.action = '/api/v1/auth/logout'
    document.body.appendChild(form)
    form.submit()
  }

  function onSessionExpired(): void {
    user.value = null
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('auth:expired', onSessionExpired)
  }

  return { user, loading, error, isAuthenticated, isEditor, isAdmin, isLocalUser, loadUser, redirectToLogin, logout }
})
