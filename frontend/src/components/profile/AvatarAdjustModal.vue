<template>
  <n-modal
    :show="show"
    preset="card"
    :title="t('users.profile.avatarAdjust.title')"
    class="avatar-adjust"
    :style="{ width: '380px' }"
    :mask-closable="true"
    @update:show="$emit('update:show', $event)"
  >
    <div
      ref="previewRef"
      class="avatar-adjust__preview"
      :class="{ 'avatar-adjust__preview--dragging': dragging }"
      role="application"
      :aria-label="t('users.profile.avatarAdjust.focal')"
      tabindex="0"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @keydown="onKeydown"
      @wheel.prevent="onWheel"
    >
      <img
        :src="avatarUrl ?? undefined"
        class="avatar-adjust__img"
        :style="previewImageStyle"
        alt=""
        draggable="false"
      >
      <div
        class="avatar-adjust__focal"
        :style="{ left: markerX + '%', top: markerY + '%' }"
      />
    </div>

    <div class="avatar-adjust__hint">
      {{ t('users.profile.avatarAdjust.hint') }}
    </div>

    <div class="avatar-adjust__zoom">
      <span class="avatar-adjust__zoom-label">{{ t('users.profile.avatarAdjust.zoom') }}</span>
      <n-slider
        v-model:value="zoomValue"
        :min="100"
        :max="300"
        :step="5"
        :format-tooltip="formatZoomTooltip"
        @update:value="setZoom"
      />
    </div>

    <template #footer>
      <div class="avatar-adjust__footer">
        <n-button
          size="small"
          quaternary
          @click="resetFocal"
        >
          {{ t('users.profile.avatarAdjust.reset') }}
        </n-button>
        <n-button
          size="small"
          type="primary"
          @click="$emit('update:show', false)"
        >
          {{ t('common.done') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
/**
 * Подгонка аватара после загрузки: фокальная точка (drag) + зум (слайдер /
 * колесо) — самописный редактор по образцу NewsCoverUpload.vue (обложки
 * новостей). Персист debounce 350 мс через PATCH профиля: свой —
 * /users/me/profile, чужой (admin из профиля пользователя) —
 * /users/admin/{id}/profile.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NModal, NSlider, useMessage } from 'naive-ui'
import { adminPatchUserProfile, patchMyProfile } from '../../api/users'
import { parseApiError } from '../../utils/parseApiError'
import { clampFocalCoord, clampFocalZoom, focalImageStyle } from '../../utils/coverFocal'

const props = defineProps<{
  show: boolean
  avatarUrl: string | null
  focalX: number | null
  focalY: number | null
  focalZoom: number | null
  /** true — PATCH своего профиля; false — admin-режим для userId. */
  isOwn: boolean
  userId?: string
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'saved', focal: { x: number | null; y: number | null; zoom: number | null }): void
}>()

const { t } = useI18n()
const message = useMessage()

const focalX = ref<number | null>(props.focalX)
const focalY = ref<number | null>(props.focalY)
const focalZoom = ref<number | null>(props.focalZoom)
const dragging = ref(false)
const previewRef = ref<HTMLElement | null>(null)

// При каждом открытии — стартуем с актуальных значений пользователя.
watch(
  () => props.show,
  (show) => {
    if (show) {
      focalX.value = props.focalX
      focalY.value = props.focalY
      focalZoom.value = props.focalZoom
    }
  },
)

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
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    const payload = {
      avatar_focal_x: focalX.value,
      avatar_focal_y: focalY.value,
      avatar_focal_zoom: focalZoom.value,
    }
    try {
      if (props.isOwn) {
        await patchMyProfile(payload)
      } else {
        if (!props.userId) return
        await adminPatchUserProfile(props.userId, payload)
      }
      emit('saved', { x: focalX.value, y: focalY.value, zoom: focalZoom.value })
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

function onWheel(e: WheelEvent) {
  setZoom(zoomValue.value + (e.deltaY < 0 ? 10 : -10))
}

function resetFocal() {
  focalX.value = null
  focalY.value = null
  focalZoom.value = null
  schedulePersist()
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

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
})
</script>

<style scoped>
.avatar-adjust__preview {
  position: relative;
  width: 220px;
  height: 220px;
  margin: 0 auto;
  border-radius: 50%;
  overflow: hidden;
  cursor: crosshair;
  touch-action: none;
  border: 3px solid var(--color-border);
}
.avatar-adjust__preview:focus-visible {
  outline: 2px solid var(--color-brand-sky);
  outline-offset: 2px;
}
.avatar-adjust__preview--dragging {
  cursor: grabbing;
}
.avatar-adjust__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  user-select: none;
  -webkit-user-drag: none;
}
.avatar-adjust__focal {
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
.avatar-adjust__hint {
  margin: 10px 0 8px;
  font-size: 11px;
  color: var(--color-text-subtle);
  line-height: 1.4;
  text-align: center;
}
.avatar-adjust__zoom {
  display: flex;
  align-items: center;
  gap: 10px;
}
.avatar-adjust__zoom-label {
  font-size: 11px;
  color: var(--color-text-subtle);
  white-space: nowrap;
}
.avatar-adjust__footer {
  display: flex;
  justify-content: space-between;
}
</style>
