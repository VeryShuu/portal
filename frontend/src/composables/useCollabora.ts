import { ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { openInCollabora, type NCItem } from '../api/files'

export function useCollabora(folderId: Ref<string | null>): {
  openingCollaboraFile: Ref<string | null>
  openCollabora(item: NCItem): Promise<void>
} {
  const { t } = useI18n()
  const message = useMessage()

  const openingCollaboraFile = ref<string | null>(null)

  async function openCollabora(item: NCItem) {
    if (!folderId.value || openingCollaboraFile.value === item.name) return
    openingCollaboraFile.value = item.name
    try {
      const resp = await openInCollabora(folderId.value, item.name)
      window.open(resp.url, '_blank', 'noopener,noreferrer')
    } catch {
      message.error(t('files.error.collabora'))
    } finally {
      openingCollaboraFile.value = null
    }
  }

  return { openingCollaboraFile, openCollabora }
}
