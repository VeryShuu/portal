import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'

export interface ModuleSettingsResponse {
  nextcloud: { enabled: boolean }
  photos: { enabled: boolean }
}

const TTL_MS = 60_000

export const useModulesStore = defineStore('modules', () => {
  const data = ref<ModuleSettingsResponse | null>(null)
  const loadedAt = ref(0)

  async function load(force = false): Promise<ModuleSettingsResponse> {
    const now = Date.now()
    if (!force && data.value && now - loadedAt.value < TTL_MS) {
      return data.value
    }
    data.value = await api<ModuleSettingsResponse>('/modules')
    loadedAt.value = now
    return data.value
  }

  function isEnabled(moduleName: 'nextcloud' | 'photos'): boolean {
    if (!data.value) return false
    return data.value[moduleName].enabled
  }

  return {
    data,
    load,
    isEnabled,
  }
})
