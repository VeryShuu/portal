<template>
  <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -->
  <div
    class="attachments-panel"
    :class="{ 'is-dragover': canUpload && isDragOver }"
    role="region"
    @dragover.prevent="onDragOver"
    @dragenter.prevent="onDragOver"
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <div class="attachments-header">
      <span class="attachments-title">{{ t('kb.files.title') }}</span>
      <label
        v-if="canUpload"
        class="upload-btn"
        :for="inputId"
      >
        <n-button
          size="small"
          type="default"
          :loading="uploading"
          tag="span"
        >
          {{ t('kb.files.attach') }}
        </n-button>
        <input
          :id="inputId"
          type="file"
          multiple
          style="display:none"
          :aria-label="t('kb.files.attach')"
          @change="handleFileChange"
        >
      </label>
    </div>

    <div
      v-if="files.length"
      class="attachments-list"
    >
      <div
        v-for="f in files"
        :key="f.id"
        class="attachment-row"
      >
        <span class="attachment-icon">{{ mimeIcon(f.mime_type) }}</span>
        <a
          class="attachment-name"
          :href="`/api/v1/kb/files/${articleId}/${encodeURIComponent(f.filename)}`"
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
          :aria-label="t('kb.files.delete')"
          @click="deleteFile(f)"
        >
          ✕
        </n-button>
      </div>
    </div>
    <p
      v-if="canUpload"
      class="attachments-hint"
    >
      {{ t('kb.files.dropHint') }}
    </p>
    <div
      v-else-if="!files.length"
      class="attachments-empty"
    >
      {{ t('kb.files.empty') }}
    </div>

    <div
      v-if="canUpload && isDragOver"
      class="attachments-dropzone"
    >
      {{ t('kb.files.dropHere') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage, NButton } from 'naive-ui'
import {
  fetchAttachments,
  uploadAttachment,
  deleteAttachment,
  type KbFile,
} from '../api/kb'
import { formatSize } from '@/utils/formatSize'
import { parseApiError } from '@/utils/parseApiError'
import { useFileDropzone } from '../composables/useFileDropzone'

const props = defineProps<{
  articleId: string
  canUpload?: boolean
}>()

const inputId = computed(() => `kb-attach-input-${props.articleId}`)

const emit = defineEmits<{
  (e: 'files-loaded', count: number): void
}>()

const { t } = useI18n()
const message = useMessage()

const files = ref<KbFile[]>([])
const uploading = ref(false)
const deletingId = ref<string | null>(null)

const { isDragOver, onDragOver, onDragLeave, onDrop } = useFileDropzone({
  enabled: () => !!props.canUpload,
  onFiles: uploadFiles,
})

onMounted(loadFiles)

watch(() => props.articleId, loadFiles)

async function loadFiles() {
  if (!props.articleId) return
  try {
    const data = await fetchAttachments(props.articleId)
    files.value = data?.items || []
  } catch {
    files.value = []
  }
  emit('files-loaded', files.value?.length || 0)
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files ?? [])
  if (!selected.length) return
  input.value = ''
  await uploadFiles(selected)
}

async function uploadFiles(toUpload: File[]) {
  if (uploading.value || !props.canUpload) return
  uploading.value = true
  let uploaded = 0
  try {
    for (const file of toUpload) {
      const formData = new FormData()
      formData.append('file', file)
      await uploadAttachment(props.articleId, formData)
      uploaded++
    }
  } catch (err) {
    message.error(parseApiError(err, t))
  } finally {
    await loadFiles()
    uploading.value = false
    if (uploaded > 0) message.success(t('kb.files.uploadSuccess'))
  }
}

async function deleteFile(f: KbFile) {
  deletingId.value = f.id
  try {
    await deleteAttachment(props.articleId, f.id)
    await loadFiles()
  } catch (err) {
    message.error(parseApiError(err, t))
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

</script>

<style scoped>
.attachments-panel { position: relative; background: var(--color-surface, #fff); border: 1px solid var(--color-border, #e0e0e6); border-radius: var(--radius-lg, 12px); box-shadow: var(--shadow-sm); padding: 18px; transition: border-color 0.15s ease, background-color 0.15s ease; }
.attachments-panel.is-dragover { border-color: var(--n-primary-color, #4e7af0); border-style: dashed; background: var(--n-primary-color-suppl, rgba(78, 122, 240, 0.06)); }
.attachments-dropzone {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--n-color, #fff);
  opacity: 0.94;
  color: var(--n-primary-color, #4e7af0);
  font-weight: 600;
  font-size: 14px;
  pointer-events: none;
}
.attachments-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.attachments-title { font-weight: 600; font-size: 14px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--color-text-subtle); }
.upload-btn { cursor: pointer; }
.attachments-list { display: flex; flex-direction: column; gap: 8px; }
.attachments-hint { margin: 12px 0 0; font-size: 13px; color: var(--n-text-color-3, #999); }
.attachment-row { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.attachment-icon { font-size: 17px; flex-shrink: 0; }
.attachment-name { flex: 1; color: var(--n-primary-color, #4e7af0); text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.attachment-name:hover { text-decoration: underline; }
.attachment-size { color: var(--n-text-color-3, #999); white-space: nowrap; font-size: 13px; }
.attachments-empty { font-size: 14px; color: var(--n-text-color-3, #999); padding: 4px 0; }
</style>
