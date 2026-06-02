import { computed, onMounted } from 'vue'
import { useLinksStore } from '../../stores/links'

export function useHomeLinksPreview() {
  const linksStore = useLinksStore()

  const topLinks = computed(() => linksStore.links.slice(0, 6))

  onMounted(() => {
    linksStore.loadLinks()
  })

  return { linksStore, topLinks }
}
