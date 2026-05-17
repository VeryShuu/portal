<template>
  <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -->
  <div
    class="u-panel att-panel"
    :class="{ 'u-panel--dropping': attDropping && !!newsId }"
    role="region"
    :aria-label="t('news.attachments.title')"
    @dragover.prevent="onCardDragOver"
    @dragleave="onCardDragLeave"
    @drop.prevent="onCardDrop"
  >
    <div class="u-panel__title">
      {{ t('news.attachments.title') }}
    </div>
    <div
      v-if="!newsId"
      class="u-panel__hint"
      style="color:var(--color-warning,#f0a020)"
    >
      {{ t('news.form.saveFirst') }}
    </div>
    <div
      v-else
      class="u-panel__hint"
    >
      {{ t('news.attachments.hint') }}
    </div>

    <div
      v-if="attachments.length"
      class="att-list"
    >
      <div
        v-for="att in attachments"
        :key="att.id"
        class="att-item"
      >
        <div class="att-item__name">
          {{ att.original_name }}
        </div>
        <div class="att-item__size">
          {{ formatSize(att.file_size) }}
        </div>
        <n-button
          size="tiny"
          type="error"
          ghost
          :loading="deletingId === att.id"
          @click="handleDelete(att.id)"
        >
          <template #icon>
            <n-icon><TrashOutline /></n-icon>
          </template>
        </n-button>
      </div>
    </div>

    <n-upload
      :show-file-list="false"
      :custom-request="handleUpload"
      :disabled="uploading || !newsId"
      multiple
    >
      <n-button
        size="small"
        :loading="uploading"
        :disabled="!newsId"
        style="margin-top:10px"
      >
        <template #icon>
          <n-icon><AttachOutline /></n-icon>
        </template>
        {{ t('news.attachments.upload') }}
      </n-button>
    </n-upload>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NUpload, useMessage, type UploadCustomRequestOptions } from 'naive-ui'
import { TrashOutline, AttachOutline } from '@vicons/ionicons5'
import { useNewsAttachmentsQuery, useUploadAttachmentMutation, useDeleteAttachmentMutation } from '../queries/news'
import { parseApiError } from '../utils/parseApiError'
import { formatSize } from '../utils/formatSize'
import type { NewsAttachment } from '../api/news'

const props = defineProps<{ newsId: string | undefined }>()

const { t } = useI18n()
const message = useMessage()

const uploadMutation = useUploadAttachmentMutation()
const deleteMutation = useDeleteAttachmentMutation()

const attachments = ref<NewsAttachment[]>([])
const uploading = ref(false)
const deletingId = ref<string | null>(null)
const attDropping = ref(false)

const { data: attachmentsData } = useNewsAttachmentsQuery(
  () => props.newsId ?? '',
  { enabled: () => !!props.newsId },
)

const initialized = ref(false)
watch(attachmentsData, (atts) => {
  if (atts && !initialized.value) {
    attachments.value = [...atts]
    initialized.value = true
  }
}, { immediate: true })

async function handleUpload(options: UploadCustomRequestOptions) {
  const { file, onFinish, onError } = options
  if (!props.newsId || !file.file) { onError(); return }
  uploading.value = true
  try {
    const att = await uploadMutation.mutateAsync({ newsId: props.newsId, file: file.file })
    attachments.value.push(att)
    onFinish()
  } catch (e) {
    message.error(parseApiError(e, t))
    onError()
  } finally {
    uploading.value = false
  }
}

async function handleDelete(attId: string) {
  if (!props.newsId) return
  deletingId.value = attId
  try {
    await deleteMutation.mutateAsync({ newsId: props.newsId, attId })
    attachments.value = attachments.value.filter(a => a.id !== attId)
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    deletingId.value = null
  }
}

function onCardDragOver(e: DragEvent) {
  if (!props.newsId) return
  if (e.dataTransfer?.types.includes('Files')) attDropping.value = true
}

function onCardDragLeave(e: DragEvent) {
  const card = e.currentTarget as HTMLElement
  if (!card.contains(e.relatedTarget as Node)) attDropping.value = false
}

async function onCardDrop(e: DragEvent) {
  attDropping.value = false
  if (!props.newsId) return
  const files = Array.from(e.dataTransfer?.files ?? [])
  if (!files.length) return
  uploading.value = true
  try {
    for (const file of files) {
      const att = await uploadMutation.mutateAsync({ newsId: props.newsId, file })
      attachments.value.push(att)
    }
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.att-panel { margin-top: 16px; }
.att-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 4px;
}
.att-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--color-bg-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}
.att-item__name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.att-item__size {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
}
</style>
