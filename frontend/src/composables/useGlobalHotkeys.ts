import { onBeforeUnmount, onMounted } from 'vue'

export interface GlobalHotkeysOptions {
  onOpenSearch: () => void
}

/**
 * Registers global keyboard shortcuts:
 * - Ctrl/Cmd+K: open global search
 * - Custom 'open-global-search' window event: open global search (e.g. from HeroBlock)
 */
export function useGlobalHotkeys({ onOpenSearch }: GlobalHotkeysOptions) {
  function onKeydown(e: KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault()
      onOpenSearch()
    }
  }
  function onOpenEvent() {
    onOpenSearch()
  }

  onMounted(() => {
    if (typeof window === 'undefined') return
    window.addEventListener('keydown', onKeydown)
    window.addEventListener('open-global-search', onOpenEvent)
  })

  onBeforeUnmount(() => {
    if (typeof window === 'undefined') return
    window.removeEventListener('keydown', onKeydown)
    window.removeEventListener('open-global-search', onOpenEvent)
  })
}
