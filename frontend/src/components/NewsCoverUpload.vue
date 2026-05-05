<template>
  <div>
    <div class="cover-preview" v-if="coverImageUrl">
      <img
        :src="coverImageUrl"
        class="cover-preview__img"
        :style="{ objectPosition: focalPreviewPosition }"
        alt=""
      />
      <n-button
        class="cover-preview__del"
        size="tiny"
        type="error"
        secondary
        :loading="uploading"
        @click="handleDelete"
      >
        <template #icon><n-icon><TrashOutline /></n-icon></template>
        {{ t('news.form.coverDelete') }}
      </n-button>
    </div>

    <div v-if="coverImageUrl" class="focal-row">
      <div class="focal-row__label">{{ t('news.form.coverFocal') }}</div>
      <n-button-group size="small">
        <n-button
          :type="focalPoint === 'top' ? 'primary' : 'default'"
          :ghost="focalPoint !== 'top'"
          @click="setFocal('top')"
        >{{ t('news.form.focalTop') }}</n-button>
        <n-button
          :type="(focalPoint ?? 'center') === 'center' ? 'primary' : 'default'"
          :ghost="(focalPoint ?? 'center') !== 'center'"
          @click="setFocal('center')"
        >{{ t('news.form.focalCenter') }}</n-button>
        <n-button
          :type="focalPoint === 'bottom' ? 'primary' : 'default'"
          :ghost="focalPoint !== 'bottom'"
          @click="setFocal('bottom')"
        >{{ t('news.form.focalBottom') }}</n-button>
      </n-button-group>
      <div class="focal-row__hint">{{ t('news.form.coverFocalHint') }}</div>
    </div>

    <div v-else-if="!newsId" class="cover-drop cover-drop--disabled">
      <n-icon size="28" class="cover-drop__icon"><ImageOutline /></n-icon>
      <div class="cover-drop__label">{{ t('news.form.coverUpload') }}</div>
      <div class="cover-drop__hint" style="color:var(--color-warning,#f0a020)">{{ t('news.form.saveFirst') }}</div>
    </div>

    <n-upload
      v-else
      accept="image/jpeg,image/png,image/webp,image/gif"
      :show-file-list="false"
      :custom-request="handleUpload"
      :disabled="uploading"
    >
      <div class="cover-drop" :class="{ 'cover-drop--loading': uploading }">
        <n-icon size="28" class="cover-drop__icon"><ImageOutline /></n-icon>
        <div class="cover-drop__label">{{ t('news.form.coverUpload') }}</div>
        <div class="cover-drop__hint">{{ t('news.form.coverHint') }}</div>
      </div>
    </n-upload>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NButtonGroup,
  NIcon,
  NUpload,
  useMessage,
  type UploadCustomRequestOptions,
} from 'naive-ui'
import { ImageOutline, TrashOutline } from '@vicons/ionicons5'
import { uploadNewsCover, deleteNewsCover, updateNews } from '../api/news'
import { parseApiError } from '../utils/parseApiError'

type FocalPoint = 'top' | 'center' | 'bottom'

const props = defineProps<{
  newsId: string | undefined
  isEdit: boolean
  coverImageUrl: string | null
  focalPoint: FocalPoint | null
}>()

const emit = defineEmits<{
  'update:coverImageUrl': [url: string | null]
  'update:focalPoint': [fp: FocalPoint | null]
}>()

const { t } = useI18n()
const message = useMessage()

const uploading = ref(false)

const focalPreviewPosition = computed(() => {
  if (props.focalPoint === 'top') return '50% 0%'
  if (props.focalPoint === 'bottom') return '50% 100%'
  return '50% 50%'
})

async function setFocal(value: FocalPoint) {
  emit('update:focalPoint', value)
  if (props.isEdit && props.newsId) {
    try {
      await updateNews(props.newsId, { cover_focal_point: value })
    } catch (e) {
      message.error(parseApiError(e, t))
    }
  }
}

async function handleUpload(options: UploadCustomRequestOptions) {
  const { file, onFinish, onError } = options
  if (!props.isEdit || !props.newsId) {
    message.warning(t('news.form.coverSaveFirst'))
    onError()
    return
  }
  if (!file.file) { onError(); return }
  uploading.value = true
  try {
    const updated = await uploadNewsCover(props.newsId, file.file)
    emit('update:coverImageUrl', updated.cover_image_url)
    message.success(t('news.form.coverUploaded'))
    onFinish()
  } catch (e) {
    message.error(parseApiError(e, t))
    onError()
  } finally {
    uploading.value = false
  }
}

async function handleDelete() {
  if (!props.isEdit || !props.newsId) return
  uploading.value = true
  try {
    await deleteNewsCover(props.newsId)
    emit('update:coverImageUrl', null)
    message.success(t('news.form.coverDeleted'))
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.cover-preview {
  position: relative;
  border-radius: var(--radius-md);
  overflow: hidden;
  margin-bottom: 8px;
}
.cover-preview__img {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  display: block;
}
.cover-preview__del {
  position: absolute;
  top: 8px;
  right: 8px;
}

.focal-row {
  margin: 4px 0 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.focal-row__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
}
.focal-row__hint {
  font-size: 11px;
  color: var(--color-text-subtle);
  line-height: 1.4;
}

.cover-drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 20px 12px;
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color var(--t-base), background var(--t-base);
  text-align: center;
  margin-bottom: 8px;
}
.cover-drop:hover {
  border-color: var(--color-brand-sky);
  background: var(--color-bg-muted);
}
.cover-drop--loading {
  opacity: 0.6;
  pointer-events: none;
}
.cover-drop--disabled {
  opacity: 0.6;
  cursor: not-allowed;
  pointer-events: none;
}
.cover-drop__icon {
  color: var(--color-text-muted);
}
.cover-drop__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}
.cover-drop__hint {
  font-size: 11px;
  color: var(--color-text-subtle);
}
</style>
