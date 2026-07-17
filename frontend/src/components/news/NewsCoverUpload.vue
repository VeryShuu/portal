<template>
  <div>
    <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -->
    <div
      v-if="coverImageUrl"
      ref="previewRef"
      class="cover-preview"
      :class="{ 'cover-preview--dragging': dragging }"
      role="application"
      :aria-label="t('news.form.coverFocal')"
      tabindex="0"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @keydown="onKeydown"
      @wheel.prevent="onWheel"
    >
      <img
        :src="coverImageUrl"
        class="cover-preview__img"
        :style="previewImageStyle"
        alt=""
        draggable="false"
      >
      <div
        class="cover-preview__focal"
        :style="{ left: markerX + '%', top: markerY + '%' }"
      />
      <n-button
        class="cover-preview__del"
        size="tiny"
        type="error"
        secondary
        :loading="uploading"
        @pointerdown.stop
        @click="handleDelete"
      >
        <template #icon>
          <n-icon><TrashOutline /></n-icon>
        </template>
        {{ t('news.form.coverDelete') }}
      </n-button>
    </div>

    <div
      v-if="coverImageUrl"
      class="focal-hint"
    >
      {{ t('news.form.coverFocalHint') }}
    </div>

    <div
      v-if="coverImageUrl"
      class="focal-zoom"
    >
      <span class="focal-zoom__label">{{ t('news.form.coverZoom') }}</span>
      <n-slider
        v-model:value="zoomValue"
        :min="100"
        :max="300"
        :step="5"
        :format-tooltip="formatZoomTooltip"
        @update:value="onZoomInput"
      />
    </div>

    <div
      v-else-if="!newsId"
      class="cover-drop cover-drop--disabled"
    >
      <n-icon
        size="28"
        class="cover-drop__icon"
      >
        <ImageOutline />
      </n-icon>
      <div class="cover-drop__label">
        {{ t('news.form.coverUpload') }}
      </div>
      <div
        class="cover-drop__hint"
        style="color:var(--color-warning,#f0a020)"
      >
        {{ t('news.form.saveFirst') }}
      </div>
    </div>

    <n-upload
      v-else
      accept="image/jpeg,image/png,image/webp,image/gif"
      :show-file-list="false"
      :custom-request="handleUpload"
      :disabled="uploading"
    >
      <div
        class="cover-drop"
        :class="{ 'cover-drop--loading': uploading }"
      >
        <n-icon
          size="28"
          class="cover-drop__icon"
        >
          <ImageOutline />
        </n-icon>
        <div class="cover-drop__label">
          {{ t('news.form.coverUpload') }}
        </div>
        <div class="cover-drop__hint">
          {{ t('news.form.coverHint', { maxSizeMb: props.maxSizeMb }) }}
        </div>
      </div>
    </n-upload>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NIcon,
  NSlider,
  NUpload,
  useMessage,
  type UploadCustomRequestOptions,
} from 'naive-ui'
import { ImageOutline, TrashOutline } from '@vicons/ionicons5'
import { uploadNewsCover, deleteNewsCover, updateNews } from '../../api/news'
import { parseApiError } from '../../utils/parseApiError'
import { clampFocalCoord, clampFocalZoom, focalImageStyle } from '../../utils/coverFocal'

const props = defineProps<{
  newsId: string | undefined
  isEdit: boolean
  maxSizeMb?: number
}>()

const coverImageUrl = defineModel<string | null>('coverImageUrl', { required: true })
const focalX = defineModel<number | null>('focalX', { required: true })
const focalY = defineModel<number | null>('focalY', { required: true })
const focalZoom = defineModel<number | null>('focalZoom', { required: true })

const { t } = useI18n()
const message = useMessage()

const uploading = ref(false)
const dragging = ref(false)
const previewRef = ref<HTMLElement | null>(null)

const markerX = computed(() => focalX.value ?? 50)
const markerY = computed(() => focalY.value ?? 50)
const zoomValue = computed(() => focalZoom.value ?? 100)
const previewImageStyle = computed(() =>
  focalImageStyle(focalX.value, focalY.value, focalZoom.value),
)

function formatZoomTooltip(value: number): string {
  return `${value}%`
}

let saveTimer: ReturnType<typeof setTimeout> | null = null

function schedulePersist() {
  if (!props.isEdit || !props.newsId) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    try {
      await updateNews(props.newsId!, {
        cover_focal_x: focalX.value,
        cover_focal_y: focalY.value,
        cover_focal_zoom: focalZoom.value,
      })
    } catch (e) {
      message.error(parseApiError(e, t))
    }
  }, 350)
}

function setZoom(value: number) {
  const clamped = clampFocalZoom(value)
  focalZoom.value = clamped === 100 ? null : clamped
  schedulePersist()
}

function onZoomInput(value: number) {
  setZoom(value)
}

function onWheel(e: WheelEvent) {
  if (!coverImageUrl.value) return
  const delta = e.deltaY < 0 ? 10 : -10
  setZoom(zoomValue.value + delta)
}

function applyFromEvent(e: PointerEvent) {
  const el = previewRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return
  focalX.value = clampFocalCoord(((e.clientX - rect.left) / rect.width) * 100)
  focalY.value = clampFocalCoord(((e.clientY - rect.top) / rect.height) * 100)
}

function onPointerDown(e: PointerEvent) {
  if (!coverImageUrl.value) return
  dragging.value = true
  ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
  applyFromEvent(e)
}

function onPointerMove(e: PointerEvent) {
  if (!dragging.value) return
  applyFromEvent(e)
}

function onPointerUp(e: PointerEvent) {
  if (!dragging.value) return
  dragging.value = false
  ;(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId)
  schedulePersist()
}

function nudge(dx: number, dy: number) {
  focalX.value = clampFocalCoord(markerX.value + dx)
  focalY.value = clampFocalCoord(markerY.value + dy)
  schedulePersist()
}

function onKeydown(e: KeyboardEvent) {
  const step = e.shiftKey ? 10 : 1
  switch (e.key) {
    case 'ArrowLeft': nudge(-step, 0); break
    case 'ArrowRight': nudge(step, 0); break
    case 'ArrowUp': nudge(0, -step); break
    case 'ArrowDown': nudge(0, step); break
    default: return
  }
  e.preventDefault()
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
    coverImageUrl.value = updated.cover_image_url
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
    coverImageUrl.value = null
    message.success(t('news.form.coverDeleted'))
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    uploading.value = false
  }
}

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
})
</script>

<style scoped>
.cover-preview {
  position: relative;
  border-radius: var(--radius-md);
  overflow: hidden;
  margin-bottom: 8px;
  cursor: crosshair;
  touch-action: none;
}
.cover-preview:focus-visible {
  outline: 2px solid var(--color-brand-sky);
  outline-offset: 2px;
}
.cover-preview--dragging {
  cursor: grabbing;
}
.cover-preview__img {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  display: block;
  user-select: none;
  -webkit-user-drag: none;
}
.cover-preview__focal {
  position: absolute;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid #fff;
  background: rgba(0, 0, 0, 0.35);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.45), 0 1px 4px rgba(0, 0, 0, 0.5);
  transform: translate(-50%, -50%);
  pointer-events: none;
}
.cover-preview__del {
  position: absolute;
  top: 8px;
  right: 8px;
}

.focal-hint {
  margin: 4px 0 8px;
  font-size: 11px;
  color: var(--color-text-subtle);
  line-height: 1.4;
}

.focal-zoom {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 12px;
}
.focal-zoom__label {
  font-size: 11px;
  color: var(--color-text-subtle);
  white-space: nowrap;
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
