import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useQueryClient } from '@tanstack/vue-query'
import { useConfirmDialog } from './useConfirmDialog'
import {
  useCreateKbSectionMutation,
  useDeleteKbSectionMutation,
  useKbSectionsQuery,
  useUpdateKbSectionMutation,
} from '../queries/kb'
import { queryKeys } from '../queries/keys'
import type { KbSection } from '../api/kb'

export function useKbSections() {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()
  const createKbSectionMutation = useCreateKbSectionMutation()
  const updateKbSectionMutation = useUpdateKbSectionMutation()
  const deleteKbSectionMutation = useDeleteKbSectionMutation()

  const { data: sectionsData, isLoading: sectionsLoading } = useKbSectionsQuery()
  const sections = computed(() => sectionsData.value?.items ?? [])
  const selectedSection = ref<string | null>(null)

  const showSectionModal = ref(false)
  const sectionSaving = ref(false)
  const sectionForm = ref({ title: '', description: '', parent_id: null as string | null })

  const showSectionPermsModal = ref(false)
  const sectionPermsId = ref<string | null>(null)
  const qc = useQueryClient()

  function findSectionRecursive(nodes: KbSection[], id: string): KbSection | null {
    for (const n of nodes) {
      if (n.id === id) return n
      const found = findSectionRecursive(n.children, id)
      if (found) return found
    }
    return null
  }

  const sectionPermsInherit = computed<boolean>(() => {
    if (!sectionPermsId.value) return true
    const s = findSectionRecursive(sections.value, sectionPermsId.value)
    return s?.inherit_permissions ?? true
  })

  function patchSectionInTree(
    nodes: KbSection[],
    id: string,
    patch: Partial<KbSection>,
  ): KbSection[] {
    return nodes.map((n) => {
      if (n.id === id) return { ...n, ...patch }
      return { ...n, children: patchSectionInTree(n.children, id, patch) }
    })
  }

  function onSectionInheritChanged(v: boolean) {
    if (!sectionPermsId.value) return
    const targetId = sectionPermsId.value
    qc.setQueryData<{ items: KbSection[] }>(queryKeys.kb.sections(), (old) => {
      if (!old) return old
      return { ...old, items: patchSectionInTree(old.items, targetId, { inherit_permissions: v }) }
    })
  }

  const showMoveModal = ref(false)
  const moveSectionId = ref<string | null>(null)
  const moveSaving = ref(false)

  function openMoveSection(sectionId: string) {
    moveSectionId.value = sectionId
    showMoveModal.value = true
  }

  async function submitMoveSection(newParentId: string | null) {
    if (!moveSectionId.value) return
    moveSaving.value = true
    try {
      await updateKbSectionMutation.mutateAsync({
        id: moveSectionId.value,
        dto: { parent_id: newParentId },
      })
      showMoveModal.value = false
      moveSectionId.value = null
      message.success(t('kb.section.moveSuccess'))
    } catch {
      message.error(t('kb.section.moveError'))
    } finally {
      moveSaving.value = false
    }
  }

  function openSectionPermissions(sectionId: string) {
    sectionPermsId.value = sectionId
    showSectionPermsModal.value = true
  }

  function openCreateSection(parentId: string | null) {
    sectionForm.value = { title: '', description: '', parent_id: parentId }
    showSectionModal.value = true
  }

  async function submitCreateSection() {
    if (!sectionForm.value.title.trim()) return
    sectionSaving.value = true
    try {
      await createKbSectionMutation.mutateAsync({
        title: sectionForm.value.title.trim(),
        description: sectionForm.value.description || null,
        parent_id: sectionForm.value.parent_id,
      })
      showSectionModal.value = false
      message.success(t('kb.section.createSuccess'))
    } catch {
      message.error(t('kb.section.createError'))
    } finally {
      sectionSaving.value = false
    }
  }

  async function renameSection(payload: { id: string; title: string }) {
    try {
      await updateKbSectionMutation.mutateAsync({
        id: payload.id,
        dto: { title: payload.title },
      })
      message.success(t('kb.section.renameSuccess'))
    } catch {
      message.error(t('kb.section.renameError'))
    }
  }

  async function confirmDeleteSection(sectionId: string) {
    const ok = await confirm({
      title: t('kb.section.delete'),
      content: t('kb.section.deleteConfirm'),
      positiveText: t('common.delete'),
      negativeText: t('common.cancel'),
    })
    if (!ok) return
    try {
      await deleteKbSectionMutation.mutateAsync({ id: sectionId })
      if (selectedSection.value === sectionId) selectedSection.value = null
      message.success(t('kb.section.deleteSuccess'))
    } catch {
      message.error(t('kb.section.deleteError'))
    }
  }

  return {
    sections,
    sectionsLoading,
    selectedSection,
    showSectionModal,
    sectionSaving,
    sectionForm,
    showSectionPermsModal,
    sectionPermsId,
    sectionPermsInherit,
    onSectionInheritChanged,
    showMoveModal,
    moveSectionId,
    moveSaving,
    openSectionPermissions,
    openCreateSection,
    openMoveSection,
    submitMoveSection,
    submitCreateSection,
    renameSection,
    confirmDeleteSection,
  }
}
