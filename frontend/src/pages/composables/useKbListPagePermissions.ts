import { computed, type ComputedRef, type Ref } from 'vue'
import { findSectionRecursive } from '../../composables/useKbSections'
import type { KbSection } from '../../api/kb'

interface AuthLike {
  isEditor: boolean
}

interface Options {
  auth: AuthLike
  sections: Ref<KbSection[]>
  selectedSection: Ref<string | null>
}

export function useKbListPagePermissions({ auth, sections, selectedSection }: Options) {
  const selectedSectionNode: ComputedRef<KbSection | null> = computed(() => {
    const id = selectedSection.value
    if (!id) return null
    return findSectionRecursive(sections.value, id)
  })

  const canCreateArticle = computed(() => {
    if (auth.isEditor) return true
    const sec = selectedSectionNode.value
    if (!sec) return true
    return sec.user_permission === 'editor' || sec.user_permission === 'manager'
  })

  return { selectedSectionNode, canCreateArticle }
}
