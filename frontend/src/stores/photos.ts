import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchRecentPhotos, type Photo } from '@/api/photos'

export const usePhotosStore = defineStore('photos', () => {
  const recent = ref<Photo[]>([])
  const recentLoaded = ref(false)
  const recentLoading = ref(false)
  const configured = ref(true)

  async function loadRecent(limit = 8) {
    if (recentLoading.value) return
    recentLoading.value = true
    try {
      const items = await fetchRecentPhotos(limit)
      recent.value = items
      configured.value = true
    } catch {
      configured.value = false
      recent.value = []
    } finally {
      recentLoaded.value = true
      recentLoading.value = false
    }
  }

  return { recent, recentLoaded, recentLoading, configured, loadRecent }
})
