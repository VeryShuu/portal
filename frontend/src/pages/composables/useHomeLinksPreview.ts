import { computed, onMounted } from 'vue'
import { useLinksStore } from '../../stores/links'

export function useHomeLinksPreview() {
  const linksStore = useLinksStore()

  const topLinks = computed(() => {
    const featured = linksStore.links.filter((link) => link.show_on_home)
    const source = featured.length ? featured : linksStore.links
    // Концепт редизайна: сетка 4×2 = 8 плиток корп. сервисов.
    return source.slice(0, 8)
  })

  onMounted(() => {
    linksStore.loadLinks()
  })

  return { linksStore, topLinks }
}
