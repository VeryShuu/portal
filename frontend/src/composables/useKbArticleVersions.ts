import { computed, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useKbVersionsQuery, useRestoreKbVersionMutation } from '../queries/kb'

export function useKbArticleVersions(articleId: Ref<string>) {
  const { t } = useI18n()
  const message = useMessage()
  const versionsQuery = useKbVersionsQuery(articleId)
  const restoreMutation = useRestoreKbVersionMutation()

  const versions = computed(() => versionsQuery.data.value?.items ?? [])

  async function load() {
    await versionsQuery.refetch()
  }

  async function restore(versionNum: number) {
    try {
      await restoreMutation.mutateAsync({ articleId: articleId.value, versionNum })
      message.success(t('kb.versionRestored'))
    } catch {
      message.error(t('common.error'))
    }
  }

  return { versions, load, restore }
}
