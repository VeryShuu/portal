import { ref, onUnmounted, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import {
  startFolderZip,
  getZipJob,
  zipJobDownloadUrl,
  type ZipJob,
} from '@/api/photos'
import { parseApiError } from '@/utils/parseApiError'

const ZIP_POLL_INTERVAL_MS = 2000
const ZIP_POLL_LIMIT = 60

export function useZipExport(folderId: Ref<string | null>) {
  const { t } = useI18n()
  const message = useMessage()

  const zipJob = ref<ZipJob | null>(null)
  const zipPolling = ref<ReturnType<typeof setInterval> | null>(null)

  function stopZipPolling(): void {
    if (zipPolling.value !== null) {
      clearInterval(zipPolling.value)
      zipPolling.value = null
    }
  }

  function _openDownload(jobId: string): void {
    window.open(zipJobDownloadUrl(jobId), '_blank', 'noopener,noreferrer')
  }

  async function startZip(): Promise<void> {
    if (!folderId.value) return
    stopZipPolling()
    zipJob.value = null
    try {
      const job = await startFolderZip(folderId.value)
      zipJob.value = job
      if (job.status === 'done') {
        _openDownload(job.id)
        message.success(t('photos.zip.ready'))
        return
      }
      if (job.status === 'error') {
        message.error(t('photos.zip.error'))
        return
      }
      let attempts = 0
      zipPolling.value = setInterval(async () => {
        attempts++
        if (attempts > ZIP_POLL_LIMIT) {
          stopZipPolling()
          zipJob.value = null
          message.error(t('photos.zip.timeout'))
          return
        }
        try {
          const updated = await getZipJob(zipJob.value!.id)
          zipJob.value = updated
          if (updated.status === 'done') {
            stopZipPolling()
            _openDownload(updated.id)
            message.success(t('photos.zip.ready'))
          } else if (updated.status === 'error') {
            stopZipPolling()
            message.error(t('photos.zip.error'))
          }
        } catch (e) {
          stopZipPolling()
          message.error(parseApiError(e, t))
        }
      }, ZIP_POLL_INTERVAL_MS)
    } catch (e) {
      message.error(parseApiError(e, t))
    }
  }

  onUnmounted(() => {
    stopZipPolling()
  })

  return {
    zipJob,
    startZip,
    stopZipPolling,
  }
}
