<template>
  <div class="attachments-panel">
    <div class="attachments-header">
      <span class="attachments-title">{{ t('kb.files.title') }}</span>
      <label v-if="canUpload" class="upload-btn">
        <n-button size="small" type="default" :loading="uploading" tag="span">
          {{ t('kb.files.attach') }}
        </n-button>
        <input type="file" style="display:none" @change="handleFileChange" />
      </label>
    </div>

    <div v-if="files.length" class="attachments-list">
      <div v-for="f in files" :key="f.id" class="attachment-row">
        <span class="attachment-icon">{{ mimeIcon(f.mime_type) }}</span>
        <a
          class="attachment-name"
          :href="`/api/v1/kb/files/${articleId}/${f.filename}`"
          target="_blank"
          rel="noopener noreferrer"
        >{{ f.original_name }}</a>
        <span class="attachment-size">{{ formatSize(f.size_bytes) }}</span>
        <n-button
          v-if="canUpload"
          size="tiny"
          type="error"
          text
          :loading="deletingId === f.id"
          @click="deleteFile(f)"
        >✕</n-button>
      </div>
    </div>
    <div v-else class="attachments-empty">{{ t('kb.files.empty') }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage, NButton } from 'naive-ui'
import { $fetch } from 'ofetch'

const props = defineProps<{
  articleId: string
  canUpload?: boolean
}>()

const { t } = useI18n()
const message = useMessage()

interface KbFile {
  id: string
  article_id: string
  filename: string
  original_name: string
  size_bytes: number
  mime_type: string | null
  created_at: string
}

const files = ref<KbFile[]>([])
const uploading = ref(false)
const deletingId = ref<string | null>(null)

onMounted(loadFiles)

watch(() => props.articleId, loadFiles)

async function loadFiles() {
  if (!props.articleId) return
  try {
    const data = await $fetch<{ items: KbFile[] }>(
      `/api/v1/kb/articles/${props.articleId}/files`,
      { credentials: 'include' }
    )
    files.value = data.items
  } catch {
    files.value = []
  }
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''

  uploading.value = true
  const formData = new FormData()
  formData.append('file', file)
  try {
    await $fetch(`/api/v1/kb/articles/${props.articleId}/files`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
    })
    await loadFiles()
    message.success(t('kb.files.uploadSuccess'))
  } catch {
    message.error(t('kb.files.uploadError'))
  } finally {
    uploading.value = false
  }
}

async function deleteFile(f: KbFile) {
  deletingId.value = f.id
  try {
    await $fetch(`/api/v1/kb/articles/${props.articleId}/files/${f.id}`, {
      method: 'DELETE',
      credentials: 'include',
    })
    await loadFiles()
  } catch {
    message.error(t('common.deleteError'))
  } finally {
    deletingId.value = null
  }
}

function mimeIcon(mime: string | null): string {
  if (!mime) return '📎'
  if (mime.startsWith('image/')) return '🖼'
  if (mime.includes('pdf')) return '📄'
  if (mime.includes('word') || mime.includes('docx')) return '📝'
  if (mime.includes('excel') || mime.includes('xlsx')) return '📊'
  if (mime.includes('zip') || mime.includes('archive')) return '🗜'
  return '📎'
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<style scoped>
.attachments-panel { border: 1px solid var(--n-border-color, #e0e0e6); border-radius: 8px; padding: 12px 16px; }
.attachments-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.attachments-title { font-weight: 600; font-size: 14px; }
.upload-btn { cursor: pointer; }
.attachments-list { display: flex; flex-direction: column; gap: 6px; }
.attachment-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.attachment-icon { font-size: 16px; flex-shrink: 0; }
.attachment-name { flex: 1; color: var(--n-primary-color, #4e7af0); text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.attachment-name:hover { text-decoration: underline; }
.attachment-size { color: var(--n-text-color-3, #999); white-space: nowrap; }
.attachments-empty { font-size: 13px; color: var(--n-text-color-3, #999); padding: 4px 0; }
</style>
