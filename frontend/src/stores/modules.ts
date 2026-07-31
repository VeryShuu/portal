import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api'
import type { GalleryLinks } from '../api/bootstrap'

export interface MeetingsModuleSettings {
  enabled: boolean
  calendar_start_hour: number
  calendar_end_hour: number
  max_recurrence_horizon_days: number
  min_search_chars: number
}

export interface ModuleSettingsResponse {
  nextcloud: { enabled: boolean }
  photos: { enabled: boolean }
  meetings: MeetingsModuleSettings
  directories: { enabled: boolean }
  signature: { enabled: boolean }
  helpdesk: { enabled: boolean }
  erp_sync: { enabled: boolean }
}

export type { GalleryLinks }

const TTL_MS = 60_000

const _DEFAULT_GALLERY: GalleryLinks = {
  photo_gallery_url: null,
  photo_gallery_mode: 'external',
  photo_gallery_new_tab: false,
  video_gallery_url: null,
}

export const useModulesStore = defineStore('modules', () => {
  const data = ref<ModuleSettingsResponse | null>(null)
  const loadedAt = ref(0)
  const galleryLinks = ref<GalleryLinks>({ ..._DEFAULT_GALLERY })

  async function load(force = false): Promise<ModuleSettingsResponse> {
    const now = Date.now()
    if (!force && data.value && now - loadedAt.value < TTL_MS) {
      return data.value
    }
    data.value = await api<ModuleSettingsResponse>('/modules')
    loadedAt.value = now
    return data.value
  }

  function setData(modules: ModuleSettingsResponse): void {
    data.value = modules
    loadedAt.value = Date.now()
  }

  function setGalleryLinks(links: GalleryLinks): void {
    galleryLinks.value = links
  }

  function isEnabled(
    moduleName:
      | 'nextcloud'
      | 'photos'
      | 'meetings'
      | 'directories'
      | 'signature'
      | 'helpdesk'
      | 'erp_sync',
  ): boolean {
    if (!data.value) return false
    return !!data.value[moduleName]?.enabled
  }

  const meetingsSettings = computed<MeetingsModuleSettings>(() =>
    data.value?.meetings ?? {
      enabled: false,
      calendar_start_hour: 8,
      calendar_end_hour: 19,
      max_recurrence_horizon_days: 31,
      min_search_chars: 3,
    },
  )

  return {
    data,
    galleryLinks,
    meetingsSettings,
    load,
    setData,
    setGalleryLinks,
    isEnabled,
  }
})
