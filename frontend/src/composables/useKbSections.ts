import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useConfirmDialog } from './useConfirmDialog'
import {
  useCreateKbSectionMutation,
  useDeleteKbSectionMutation,
  useKbSectionsQuery,
} from '../queries/kb'

export function useKbSections() {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()
  const createKbSectionMutation = useCreateKbSectionMutation()
  const deleteKbSectionMutation = useDeleteKbSectionMutation()

  const { data: sectionsData, isLoading: sectionsLoading } = useKbSectionsQuery()
  const sections = computed(() => sectionsData.value?.items ?? [])
  const selectedSection = ref<string | null>(null)

  const showSectionModal = ref(false)
  const sectionSaving = ref(false)
  const sectionForm = ref({ title: '', description: '', parent_id: null as string | null })

  const showSectionPermsModal = ref(false)
  const sectionPermsId = ref<string | null>(null)

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
    openSectionPermissions,
    openCreateSection,
    submitCreateSection,
    confirmDeleteSection,
  }
}
