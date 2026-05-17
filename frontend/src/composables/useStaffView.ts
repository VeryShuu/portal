import { computed, ref } from 'vue'
import { useBreakpoints } from './useBreakpoints'

type ViewMode = 'table' | 'grid'

const STORAGE_VIEW = 'staff:view'

export function useStaffView() {
  const { isMobile } = useBreakpoints()

  function readStoredView(): ViewMode {
    try {
      const v = localStorage.getItem(STORAGE_VIEW)
      if (v === 'grid' || v === 'table') return v
    } catch { /* ignore */ }
    return 'table'
  }

  const view = ref<ViewMode>(readStoredView())
  const effectiveView = computed<ViewMode>(() => (isMobile.value ? 'grid' : view.value))

  function setView(v: ViewMode) {
    view.value = v
    try {
      localStorage.setItem(STORAGE_VIEW, v)
    } catch { /* ignore */ }
  }

  return { view, effectiveView, setView, isMobile }
}
