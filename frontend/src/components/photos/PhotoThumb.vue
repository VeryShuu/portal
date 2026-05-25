<template>
  <div
    class="photo-thumb"
    :class="{ 'photo-thumb--ready': loaded }"
    :aria-label="alt"
  >
    <canvas
      v-if="blurhash && !loaded"
      ref="canvasRef"
      class="photo-thumb__blur"
      :width="BLUR_W"
      :height="BLUR_H"
      aria-hidden="true"
    />
    <div
      v-else-if="!blurhash && !loaded && !previewUrl"
      class="photo-thumb__placeholder"
      aria-hidden="true"
    />
    <img
      v-if="!processed && previewUrl"
      :src="previewUrl"
      :alt="alt"
      class="photo-thumb__img photo-thumb__img--loaded photo-thumb__img--preview"
      :draggable="draggable"
    >
    <div
      v-if="!processed"
      class="photo-thumb__pending"
      :title="t('photos.processing')"
      aria-hidden="true"
    >
      <svg
        class="photo-thumb__spinner"
        viewBox="0 0 24 24"
        xmlns="http://www.w3.org/2000/svg"
      ><circle
        cx="12"
        cy="12"
        r="9"
        fill="none"
        stroke="rgba(255,255,255,0.3)"
        stroke-width="3"
      /><path
        d="M21 12a9 9 0 0 1-9 9"
        fill="none"
        stroke="#fff"
        stroke-width="3"
        stroke-linecap="round"
      /></svg>
    </div>
    <picture
      v-if="processed"
      class="photo-thumb__pic"
    >
      <source
        v-if="avif && useAvif"
        type="image/avif"
        :srcset="srcset(avif)"
        :sizes="sizesAttr"
      >
      <source
        type="image/webp"
        :srcset="srcset(webp)"
        :sizes="sizesAttr"
      >
      <img
        :src="webp(photoId, primarySize)"
        :alt="alt"
        :loading="loading"
        :draggable="draggable"
        class="photo-thumb__img"
        :class="{ 'photo-thumb__img--loaded': loaded }"
        @load="onLoad"
        @error="onError"
      >
    </picture>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { decode as decodeBlurhash } from 'blurhash'

const { t } = useI18n()

type ThumbSize = 200 | 400 | 600 | 1000 | 1600
type ThumbUrlFn = (id: string, size: ThumbSize) => string

// LRU-кэш декодированных пикселей blurhash по ключу `${hash}:${w}x${h}` (#F-5).
// Map в JS поддерживает порядок вставки — переиспользуем для дешёвого LRU.
const _BLUR_CACHE_MAX = 100
const _blurhashCache = new Map<string, Uint8ClampedArray>()
function _cachedDecode(hash: string, w: number, h: number): Uint8ClampedArray | null {
  const key = `${hash}:${w}x${h}`
  const hit = _blurhashCache.get(key)
  if (hit) {
    _blurhashCache.delete(key)
    _blurhashCache.set(key, hit)
    return hit
  }
  try {
    const pixels = decodeBlurhash(hash, w, h)
    _blurhashCache.set(key, pixels)
    if (_blurhashCache.size > _BLUR_CACHE_MAX) {
      const oldest = _blurhashCache.keys().next().value
      if (oldest !== undefined) _blurhashCache.delete(oldest)
    }
    return pixels
  } catch {
    return null
  }
}

interface Props {
  photoId: string
  processed?: boolean
  blurhash?: string | null
  previewUrl?: string | null
  alt?: string
  loading?: 'lazy' | 'eager'
  draggable?: boolean
  sizes: ThumbSize[]
  sizesAttr?: string
  avif?: ThumbUrlFn
  webp: ThumbUrlFn
}

const props = withDefaults(defineProps<Props>(), {
  processed: true,
  blurhash: null,
  previewUrl: null,
  alt: '',
  loading: 'lazy',
  draggable: false,
  sizesAttr: undefined,
  avif: undefined,
})

const BLUR_W = 32
const BLUR_H = 32
// Backend генерирует AVIF только для размеров >= AVIF_MIN_SIZE (1000).
// Если все размеры меньше — не предлагать AVIF источник, иначе 404 + broken image
// (browser не делает фолбэк на следующий <source> при 404 выбранного источника).
const AVIF_MIN_SIZE: ThumbSize = 1000

const canvasRef = ref<HTMLCanvasElement | null>(null)
const loaded = ref(false)
const primarySize = computed<ThumbSize>(() => props.sizes[0])
const useAvif = computed(() => props.sizes.some((s) => s >= AVIF_MIN_SIZE))

function srcset(fn: ThumbUrlFn) {
  if (props.sizes.length === 1) return fn(props.photoId, props.sizes[0])
  return props.sizes.map((s) => `${fn(props.photoId, s)} ${s}w`).join(', ')
}

function onLoad() {
  loaded.value = true
}

function onError() {
  loaded.value = false
}

function paintBlurhash() {
  const canvas = canvasRef.value
  if (!canvas || !props.blurhash) return
  const pixels = _cachedDecode(props.blurhash, BLUR_W, BLUR_H)
  if (!pixels) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const imgData = ctx.createImageData(BLUR_W, BLUR_H)
  imgData.data.set(pixels)
  ctx.putImageData(imgData, 0, 0)
}

watch(
  () => [props.photoId, props.blurhash] as const,
  () => {
    loaded.value = false
    // Wait next tick for canvas to mount when blurhash appears
    requestAnimationFrame(paintBlurhash)
  },
)

onMounted(paintBlurhash)
</script>

<style scoped>
.photo-thumb {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: var(--color-bg-muted);
  border-radius: inherit;
}
.photo-thumb__blur,
.photo-thumb__placeholder {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
}
.photo-thumb__blur {
  filter: blur(8px);
  transform: scale(1.1);
}
.photo-thumb__placeholder {
  background: linear-gradient(90deg, var(--color-bg-muted) 25%, var(--color-border) 50%, var(--color-bg-muted) 75%);
  background-size: 200% 100%;
  animation: photoThumbShimmer 1.6s infinite;
}
.photo-thumb__pic {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
}
.photo-thumb__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  opacity: 0;
  transition: opacity 220ms ease-out;
}
.photo-thumb__img--loaded {
  opacity: 1;
}
.photo-thumb__img--preview {
  position: absolute;
  inset: 0;
  filter: saturate(0.95);
}
.photo-thumb__pending {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
  border-radius: 50%;
  backdrop-filter: blur(4px);
  z-index: 2;
  pointer-events: none;
}
.photo-thumb__spinner {
  width: 18px;
  height: 18px;
  display: block;
  animation: photoThumbSpin 0.9s linear infinite;
  transform-origin: 50% 50%;
}
@keyframes photoThumbShimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
@keyframes photoThumbSpin {
  to { transform: rotate(360deg); }
}
</style>
