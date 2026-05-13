import { onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { importScan, getImportScanStatus } from '@/api/photos'
import { useConfirmDialog } from '@/composables/useConfirmDialog'

const POLL_INTERVAL_MS = 2000

export function useImportScan(onTreeChanged: () => Promise<void>) {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()

  let timer: ReturnType<typeof setTimeout> | null = null

  async function confirmImportScan(): Promise<void> {
    const ok = await confirm({
      title: t('photos.import.button'),
      content: t('photos.import.confirm'),
      positiveText: t('common.confirm'),
      negativeText: t('common.cancel'),
    })
    if (!ok) return
    try {
      const job = await importScan()
      message.info(t('photos.import.queued'))
      const poll = async () => {
        const s = await getImportScanStatus(job.job_id)
        if (s.status === 'complete') {
          timer = null
          if (s.result) {
            message.success(t('photos.import.done', {
              photos: s.result.photos_imported,
              folders: s.result.folders_created,
              skipped: s.result.skipped,
            }))
          }
          await onTreeChanged()
        } else if (s.status === 'queued' || s.status === 'in_progress' || s.status === 'deferred') {
          timer = setTimeout(poll, POLL_INTERVAL_MS)
        } else {
          timer = null
          message.error(t('errors.generic'))
        }
      }
      timer = setTimeout(poll, POLL_INTERVAL_MS)
    } catch {
      message.error(t('errors.generic'))
    }
  }

  onUnmounted(() => {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  })

  return { confirmImportScan }
}
