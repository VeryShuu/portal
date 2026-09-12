import { ref } from 'vue'
import type { KbViewMode } from '../../components/KbListToolbar.vue'

const VIEW_MODE_KEY = 'kb:viewMode'

function readViewMode(): KbViewMode {
  if (typeof window === 'undefined') return 'list'
  const v = window.localStorage.getItem(VIEW_MODE_KEY)
  return v === 'grid' ? 'grid' : 'list'
}

export function useKbListViewMode() {
  const viewMode = ref<KbViewMode>(readViewMode())

  function onViewModeChange(v: KbViewMode) {
    viewMode.value = v
    try {
      window.localStorage.setItem(VIEW_MODE_KEY, v)
    } catch {
      // ignore quota / privacy mode failures
    }
  }

  return { viewMode, onViewModeChange }
}
