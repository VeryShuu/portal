<template>
  <div class="public-photo">
    <header class="public-photo__header">
      <h1>{{ portalName }}</h1>
    </header>

    <main v-if="loading" class="public-photo__state">{{ t('common.loading') }}</main>
    <main v-else-if="error" class="public-photo__state public-photo__state--error">
      {{ errorMessage }}
    </main>
    <main v-else-if="photo" class="public-photo__main">
      <div class="public-photo__stage" @wheel.prevent="onWheel">
        <img
          :src="thumbSrc"
          :alt="photo.original_name"
          class="public-photo__img"
          :style="imgStyle"
        />
      </div>

      <div class="public-photo__toolbar">
        <button class="lb-btn" :title="t('photos.lightbox.zoomOut')" @click="zoomOut">−</button>
        <span class="lb-zoom">{{ Math.round(zoom * 100) }}%</span>
        <button class="lb-btn" :title="t('photos.lightbox.zoomIn')" @click="zoomIn">+</button>
        <button class="lb-btn" :title="t('photos.lightbox.rotate')" @click="rotateLeft">⟲</button>
        <button class="lb-btn" :title="t('photos.lightbox.rotateRight')" @click="rotateRight">⟳</button>
        <button class="lb-btn" :title="t('photos.lightbox.reset')" @click="resetView">⤾</button>
        <a
          class="lb-btn lb-btn--link"
          :href="downloadUrl"
          :download="photo.original_name"
          :title="t('photos.lightbox.download')"
        >⬇</a>
      </div>

      <div class="public-photo__info">
        <strong>{{ photo.original_name }}</strong>
        <span v-if="photo.taken_at"> · {{ new Date(photo.taken_at).toLocaleString() }}</span>
        <span v-if="photo.width">  · {{ photo.width }}×{{ photo.height }}</span>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ofetch } from 'ofetch'
import { publicPhotoFileUrl, publicPhotoInfoUrl, publicPhotoThumbUrl, type Photo } from '@/api/photos'
import { useBrandingStore } from '@/stores/branding'

const route = useRoute()
const { t } = useI18n()
const branding = useBrandingStore()

const token = computed(() => String(route.params.token || ''))
const photo = ref<Photo | null>(null)
const loading = ref(true)
const error = ref<'gone' | 'not_found' | 'generic' | null>(null)

const portalName = computed(() => branding.settings?.portal_name || 'Portal')
const errorMessage = computed(() => {
  if (error.value === 'gone') return t('photos.public.expired')
  if (error.value === 'not_found') return t('photos.public.notFound')
  return t('errors.generic')
})

const thumbSrc = computed(() => publicPhotoThumbUrl(token.value, 1600))
const downloadUrl = computed(() => publicPhotoFileUrl(token.value, true))

const zoom = ref(1)
const rotation = ref(0)
const imgStyle = computed(() => ({
  transform: `rotate(${rotation.value}deg) scale(${zoom.value})`,
  transition: 'transform 0.15s ease-out',
}))
function resetView() { zoom.value = 1; rotation.value = 0 }
function zoomIn() { zoom.value = Math.min(8, +(zoom.value + 0.25).toFixed(2)) }
function zoomOut() { zoom.value = Math.max(0.25, +(zoom.value - 0.25).toFixed(2)) }
function rotateLeft() { rotation.value = (rotation.value - 90) % 360 }
function rotateRight() { rotation.value = (rotation.value + 90) % 360 }
function onWheel(e: WheelEvent) { if (e.deltaY < 0) zoomIn(); else zoomOut() }

onMounted(async () => {
  try {
    if (!branding.settings) await branding.load()
  } catch { /* ignore */ }
  try {
    const data = await ofetch<Photo>(publicPhotoInfoUrl(token.value))
    photo.value = data
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
.public-photo {
  min-height: 100vh; background: #0a0a0a; color: #fff;
  display: flex; flex-direction: column;
}
.public-photo__header {
  padding: 14px 24px; background: rgba(0,0,0,0.6); border-bottom: 1px solid rgba(255,255,255,0.08);
}
.public-photo__header h1 { margin: 0; font-size: 16px; font-weight: 600; }
.public-photo__main { flex: 1; position: relative; display: flex; align-items: center; justify-content: center; }
.public-photo__state {
  flex: 1; display: flex; align-items: center; justify-content: center; font-size: 16px;
}
.public-photo__state--error { color: #ff6b6b; }
.public-photo__stage {
  width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; overflow: hidden;
}
.public-photo__img {
  max-width: 95vw; max-height: 80vh; object-fit: contain; user-select: none; -webkit-user-drag: none;
}
.public-photo__toolbar {
  position: fixed; top: 64px; left: 50%; transform: translateX(-50%);
  display: flex; align-items: center; gap: 6px;
  background: rgba(0,0,0,0.55); padding: 6px 10px; border-radius: 999px; z-index: 3;
}
.lb-btn {
  background: rgba(255,255,255,0.12); color: #fff; border: 0; cursor: pointer;
  width: 36px; height: 36px; border-radius: 50%; font-size: 16px;
  display: inline-flex; align-items: center; justify-content: center; text-decoration: none;
}
.lb-btn:hover { background: rgba(255,255,255,0.22); }
.lb-zoom { color: #fff; font-size: 12px; min-width: 44px; text-align: center; }
.public-photo__info {
  position: fixed; bottom: 0; left: 0; right: 0;
  background: rgba(0,0,0,0.7); color: #fff; padding: 12px 20px; font-size: 13px;
}
</style>
