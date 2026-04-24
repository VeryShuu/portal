import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchVideosConfig } from '@/api/videos'

export const useVideosStore = defineStore('videos', () => {
  const configured = ref(false)
  const publicUrl = ref('')
  const loaded = ref(false)

  const peertubeOrigin = computed(() => {
    if (!publicUrl.value) return ''
    try {
      return new URL(publicUrl.value).origin
    } catch {
      return ''
    }
  })

  async function load() {
    if (loaded.value) return
    try {
      const data = await fetchVideosConfig()
      configured.value = data.configured
      publicUrl.value = data.public_url ?? ''
    } catch {
      configured.value = false
    } finally {
      loaded.value = true
    }
  }

  return { configured, publicUrl, peertubeOrigin, loaded, load }
})
