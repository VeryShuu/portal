<template>
  <div class="pub-folder">
    <header class="pub-folder__header">
      <h1 class="pub-folder__portal">
        {{ portalName }}
      </h1>
      <span
        v-if="info"
        class="pub-folder__name"
      >{{ info.folder_name }}</span>
    </header>

    <main
      v-if="loading"
      class="pub-folder__state"
    >
      {{ t('common.loading') }}
    </main>
    <main
      v-else-if="error"
      class="pub-folder__state pub-folder__state--error"
    >
      {{ errorMessage }}
    </main>
    <main
      v-else-if="info"
      class="pub-folder__main"
    >
      <div class="pub-folder__meta">
        <h2 class="pub-folder__title">
          {{ info.folder_name }}
        </h2>
        <p class="pub-folder__count">
          {{ t('photos.public.folder.photoCount', { n: info.photos_count }) }}
        </p>
      </div>

      <PhotosGridBase
        :photos="photos"
        :loading="loadingPhotos && photos.length === 0"
        @photo-click="(_p, idx) => openLightbox(idx)"
      >
        <template #cell="{ photo }">
          <PhotoThumb
            :photo-id="photo.id"
            :processed="photo.processed"
            :blurhash="photo.blurhash"
            :alt="photo.original_name"
            :sizes="[400, 600]"
            sizes-attr="(max-width: 400px) 400px, 600px"
            :avif="avifFor"
            :webp="thumbFor"
          />
        </template>
        <template #empty>
          <p class="pub-folder__state">
            {{ t('photos.empty') }}
          </p>
        </template>
      </PhotosGridBase>

      <div
        v-if="totalPhotos > photos.length"
        class="photo-loadmore"
      >
        <button
          class="pub-folder__loadmore"
          :disabled="loadingPhotos"
          @click="loadMore"
        >
          {{ loadingPhotos ? t('common.loading') : t('common.loadMore') }}
        </button>
      </div>
    </main>

    <LightboxBase
      :model-value="lightboxIdx"
      :total="photos.length"
      :aria-label="t('photos.title')"
      @update:model-value="(v) => lightboxIdx = v"
      @close="onLightboxClose"
      @prev="resetView"
      @next="resetView"
      @wheel="onWheel"
    >
      <div
        class="lightbox__stage"
        aria-hidden="true"
        @click.self="closeLightbox"
      >
        <picture v-if="currentPhoto">
          <source
            type="image/avif"
            :srcset="publicFolderAvifUrl(token, currentPhoto.id, 1600)"
          >
          <source
            type="image/webp"
            :srcset="publicFolderThumbUrl(token, currentPhoto.id, 1600)"
          >
          <img
            :src="publicFolderThumbUrl(token, currentPhoto.id, 1600)"
            :alt="currentPhoto.original_name"
            class="lightbox__img"
            :style="imgStyle"
            @click.stop
          >
        </picture>
      </div>

      <template #toolbar>
        <div class="lightbox__toolbar">
          <button
            class="lb-btn"
            @click="zoomOut"
          >
            −
          </button>
          <span class="lb-zoom">{{ Math.round(zoom * 100) }}%</span>
          <button
            class="lb-btn"
            @click="zoomIn"
          >
            +
          </button>
          <button
            class="lb-btn"
            @click="rotateLeft"
          >
            ⟲
          </button>
          <button
            class="lb-btn"
            @click="rotateRight"
          >
            ⟳
          </button>
          <button
            class="lb-btn"
            @click="resetView"
          >
            ⤾
          </button>
        </div>
      </template>

      <template #info>
        <div
          v-if="currentPhoto"
          class="lightbox__info"
        >
          <strong>{{ currentPhoto.original_name }}</strong>
          <span v-if="currentPhoto.taken_at"> · {{ new Date(currentPhoto.taken_at).toLocaleString() }}</span>
          <span v-if="currentPhoto.width"> · {{ currentPhoto.width }}×{{ currentPhoto.height }}</span>
        </div>
      </template>
    </LightboxBase>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ofetch } from 'ofetch'
import { publicFolderInfoUrl, publicFolderPhotosUrl, publicFolderThumbUrl, publicFolderAvifUrl, type PublicFolderInfo, type Photo } from '@/api/photos'
import { useBrandingStore } from '@/stores/branding'
import { useLightboxView } from '@/composables/useLightboxView'
import PhotosGridBase from '@/components/photos/PhotosGridBase.vue'
import PhotoThumb from '@/components/photos/PhotoThumb.vue'
import LightboxBase from '@/components/photos/LightboxBase.vue'

type ThumbSize = 200 | 400 | 600 | 1000 | 1600

const route = useRoute()
const { t } = useI18n()
const branding = useBrandingStore()

const token = computed(() => String(route.params.token || ''))
const info = ref<PublicFolderInfo | null>(null)
const photos = ref<Photo[]>([])
const totalPhotos = ref(0)
const loading = ref(true)
const loadingPhotos = ref(false)
const error = ref<'gone' | 'not_found' | 'generic' | null>(null)
const page = ref(1)
const perPage = 50

const portalName = computed(() => branding.settings?.portal_name || 'Portal')
const errorMessage = computed(() => {
  if (error.value === 'gone') return t('photos.public.folder.expired')
  if (error.value === 'not_found') return t('photos.public.folder.notFound')
  return t('errors.generic')
})

const lightboxIdx = ref<number | null>(null)
const currentPhoto = computed(() => lightboxIdx.value !== null ? photos.value[lightboxIdx.value] : null)

const { zoom, imgStyle, resetView, zoomIn, zoomOut, rotateLeft, rotateRight, onLightboxWheel: onWheel } = useLightboxView()

function thumbFor(id: string, size: ThumbSize) {
  return publicFolderThumbUrl(token.value, id, size)
}
function avifFor(id: string, size: ThumbSize) {
  return publicFolderAvifUrl(token.value, id, size)
}

function openLightbox(idx: number) { lightboxIdx.value = idx; resetView() }
function closeLightbox() { lightboxIdx.value = null; resetView() }
function onLightboxClose() { resetView() }

async function loadPhotos(reset = false) {
  if (reset) { page.value = 1; photos.value = [] }
  loadingPhotos.value = true
  try {
    const data = await ofetch<{ items: Photo[]; total: number }>(
      publicFolderPhotosUrl(token.value, page.value, perPage)
    )
    if (reset) photos.value = data.items
    else photos.value = [...photos.value, ...data.items]
    totalPhotos.value = data.total
  } catch {
    // ignore
  } finally {
    loadingPhotos.value = false
  }
}

async function loadMore() {
  if (loadingPhotos.value) return
  page.value++
  await loadPhotos()
}

onMounted(async () => {
  try {
    if (!branding.settings) await branding.load()
  } catch { /* ignore */ }
  try {
    const data = await ofetch<PublicFolderInfo>(publicFolderInfoUrl(token.value))
    info.value = data
    await loadPhotos(true)
  } catch (e: unknown) {
    const status = (e as { status?: number; response?: { status?: number } })?.status
      ?? (e as { response?: { status?: number } })?.response?.status
    if (status === 410) error.value = 'gone'
    else if (status === 404) error.value = 'not_found'
    else error.value = 'generic'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.pub-folder {
  min-height: 100vh; background: var(--color-bg, #f5f5f5);
  display: flex; flex-direction: column;
}
.pub-folder__header {
  padding: 14px 24px; background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  display: flex; align-items: center; gap: 12px;
}
.pub-folder__portal { margin: 0; font-size: 16px; font-weight: 700; }
.pub-folder__name { color: var(--color-text-muted); font-size: 14px; }
.pub-folder__main { flex: 1; padding: 24px; max-width: var(--content-wide); width: 100%; margin: 0 auto; }
.pub-folder__meta { margin-bottom: 20px; }
.pub-folder__title { margin: 0 0 4px; font-size: 22px; }
.pub-folder__count { margin: 0; color: var(--color-text-muted); font-size: 13px; }
.pub-folder__state {
  flex: 1; display: flex; align-items: center; justify-content: center;
  font-size: 16px; padding: 60px 20px; color: var(--color-text-muted);
}
.pub-folder__state--error { color: var(--color-error, #e53e3e); }
.pub-folder__loadmore {
  display: block; margin: 20px auto 0; padding: 8px 20px;
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-sm); cursor: pointer; font-size: 14px;
}
.photo-loadmore { text-align: center; margin-top: 16px; }
.lightbox__stage { width: 100vw; height: 100vh; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.lightbox__img { max-width: 95vw; max-height: 90vh; object-fit: contain; user-select: none; -webkit-user-drag: none; }
.lightbox__toolbar {
  position: absolute; top: 16px; left: 50%; transform: translateX(-50%);
  display: flex; align-items: center; gap: 6px;
  background: rgba(0,0,0,0.55); padding: 6px 10px; border-radius: 999px; z-index: 3;
}
.lb-btn {
  background: rgba(255,255,255,0.12); color: #fff; border: 0; cursor: pointer;
  width: 36px; height: 36px; border-radius: 50%; font-size: 16px;
  display: inline-flex; align-items: center; justify-content: center;
}
.lb-btn:hover { background: rgba(255,255,255,0.22); }
.lb-zoom { color: #fff; font-size: 12px; min-width: 44px; text-align: center; }
.lightbox__info {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: rgba(0,0,0,0.7); color: #fff; padding: 12px 20px; font-size: 13px; z-index: 2;
}
</style>
