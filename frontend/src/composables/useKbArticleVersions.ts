import { onMounted, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { fetchVersions, type KbVersion } from '../api/kb'
import { useRestoreKbVersionMutation } from '../queries/kb'

export function useKbArticleVersions(articleId: Ref<string>) {
  const { t } = useI18n()
  const message = useMessage()
  const restoreMutation = useRestoreKbVersionMutation()

  const versions = ref<KbVersion[]>([])

  async function load() {
    const id = articleId.value
    try {
      const res = await fetchVersions(id, { limit: 50 })
      if (id !== articleId.value) return
      versions.value = res.items
    } catch {
      message.error(t('common.error'))
    }
  }

  async function restore(versionNum: number) {
    try {
      await restoreMutation.mutateAsync({ articleId: articleId.value, versionNum })
      message.success(t('kb.versionRestored'))
      await load()
    } catch {
      message.error(t('common.error'))
    }
  }

  onMounted(load)
  watch(articleId, load)

  return { versions, load, restore }
}
