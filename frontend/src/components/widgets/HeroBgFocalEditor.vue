<template>
  <div
    v-if="imageUrl"
    class="hero-focal"
  >
    <!-- Превью с перетаскиваемым маркером фокуса (механизм как NewsCoverUpload) -->
    <div
      ref="previewRef"
      class="hero-focal__preview"
      :style="{ '--marker-x': markerX + '%', '--marker-y': markerY + '%' }"
      tabindex="0"
      role="slider"
      :aria-label="t('admin.branding.heroBgFocalLabel', { x: Math.round(markerX), y: Math.round(markerY) })"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-valuenow="Math.round(markerX)"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @keydown="onKeydown"
      @wheel.prevent="onWheel"
    >
      <img
        :src="imageUrl"
        alt=""
        class="hero-focal__img"
        :style="previewStyle"
        draggable="false"
      >
      <span
        class="hero-focal__marker"
        :style="{ left: markerX + '%', top: markerY + '%' }"
        aria-hidden="true"
      />
    </div>

    <!-- Zoom-слайдер -->
    <div class="hero-focal__zoom">
      <span class="hero-focal__zoom-label">{{ t('admin.branding.heroBgZoom') }}</span>
      <n-slider
        :value="zoomValue"
        :min="100"
        :max="300"
        :step="5"
        :format-tooltip="(v: number) => `${v}%`"
        @update:value="onZoomChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NSlider } from 'naive-ui'
import { clampFocalCoord, clampFocalZoom, focalImageStyle } from '../../utils/coverFocal'

const { t } = useI18n()

const props = defineProps<{
  imageUrl: string | null
}>()

const focalX = defineModel<number | null | undefined>('focalX', { required: true })
const focalY = defineModel<number | null | undefined>('focalY', { required: true })
const focalZoom = defineModel<number | null | undefined>('focalZoom', { required: true })

const previewRef = ref<HTMLDivElement | null>(null)
const dragging = ref(false)

const markerX = computed(() => (focalX.value == null ? 50 : clampFocalCoord(focalX.value)))
const markerY = computed(() => (focalY.value == null ? 50 : clampFocalCoord(focalY.value)))
const zoomValue = computed(() => (focalZoom.value == null ? 100 : clampFocalZoom(focalZoom.value)))

const previewStyle = computed(() => focalImageStyle(focalX.value, focalY.value, focalZoom.value))

function applyFromEvent(e: PointerEvent) {
  const el = previewRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return
  focalX.value = clampFocalCoord(((e.clientX - rect.left) / rect.width) * 100)
  focalY.value = clampFocalCoord(((e.clientY - rect.top) / rect.height) * 100)
}

function onPointerDown(e: PointerEvent) {
  if (!props.imageUrl) return
  dragging.value = true
  ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
  applyFromEvent(e)
}
function onPointerMove(e: PointerEvent) {
  if (!dragging.value) return
  applyFromEvent(e)
}
function onPointerUp() {
  dragging.value = false
}

// Клавиатурное nudging: стрелки = 1%, Shift+стрелки = 10%
function onKeydown(e: KeyboardEvent) {
  const step = e.shiftKey ? 10 : 1
  const curX = focalX.value == null ? 50 : focalX.value
  const curY = focalY.value == null ? 50 : focalY.value
  let nx = curX
  let ny = curY
  switch (e.key) {
    case 'ArrowLeft': nx = clampFocalCoord(curX - step); break
    case 'ArrowRight': nx = clampFocalCoord(curX + step); break
    case 'ArrowUp': ny = clampFocalCoord(curY - step); break
    case 'ArrowDown': ny = clampFocalCoord(curY + step); break
    default: return
  }
  e.preventDefault()
  focalX.value = nx
  focalY.value = ny
}

// Колесо мыши = zoom
function onWheel(e: WheelEvent) {
  const delta = e.deltaY > 0 ? -5 : 5
  const next = clampFocalZoom(zoomValue.value + delta)
  focalZoom.value = next === 100 ? null : next
}

function onZoomChange(v: number) {
  focalZoom.value = v === 100 ? null : v
}
</script>

<style scoped>
.hero-focal {
  margin-top: 8px;
}
.hero-focal__preview {
  position: relative;
  width: 100%;
  aspect-ratio: 21 / 9; /* пропорция Hero */
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--color-bg-muted);
  cursor: crosshair;
  touch-action: none; /* не скроллить страницу при drag на тачскрине */
  outline: none;
}
.hero-focal__preview:focus-visible {
  outline: 2px solid var(--color-brand-sky);
  outline-offset: 2px;
}
.hero-focal__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  pointer-events: none;
  user-select: none;
}
.hero-focal__marker {
  position: absolute;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid #fff;
  background: rgba(31, 78, 140, 0.6);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.4), 0 1px 4px rgba(0, 0, 0, 0.3);
  transform: translate(-50%, -50%);
  pointer-events: none;
}
.hero-focal__zoom {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.hero-focal__zoom-label {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
}
</style>
