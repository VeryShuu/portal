<template>
  <div
    class="lightbox__toolbar"
    @click.stop
  >
    <button
      class="lb-btn"
      :title="t('photos.lightbox.zoomOut')"
      @click="$emit('zoom-out')"
    >
      −
    </button>
    <span class="lb-zoom">{{ Math.round(zoom * 100) }}%</span>
    <button
      class="lb-btn"
      :title="t('photos.lightbox.zoomIn')"
      @click="$emit('zoom-in')"
    >
      +
    </button>
    <button
      class="lb-btn"
      :title="t('photos.lightbox.rotate')"
      @click="$emit('rotate-left')"
    >
      ⟲
    </button>
    <button
      class="lb-btn"
      :title="t('photos.lightbox.rotateRight')"
      @click="$emit('rotate-right')"
    >
      ⟳
    </button>
    <button
      class="lb-btn"
      :title="t('photos.lightbox.reset')"
      @click="$emit('reset-view')"
    >
      ⤾
    </button>
    <n-dropdown
      :options="slideshowOptions"
      trigger="click"
      @select="$emit('select-slideshow', $event)"
    >
      <button
        class="lb-btn"
        :class="{ 'lb-btn--active': slideshowActive }"
        :title="slideshowActive ? t('photos.lightbox.slideshowStop') : t('photos.lightbox.slideshow')"
      >
        {{ slideshowActive ? '⏸' : '▶' }}
      </button>
    </n-dropdown>
    <a
      v-if="currentPhoto"
      class="lb-btn lb-btn--link"
      :href="originalUrl(currentPhoto.id, true)"
      :download="currentPhoto.original_name"
      :title="t('photos.lightbox.download')"
    >⬇</a>
    <button
      class="lb-btn"
      :title="t('photos.lightbox.copyLink')"
      @click="$emit('copy-link')"
    >
      🔗
    </button>
    <button
      v-if="canUpload"
      class="lb-btn"
      :title="t('photos.lightbox.createShareLink')"
      :disabled="creatingShare"
      @click="$emit('open-share-modal')"
    >
      🌐
    </button>
    <button
      v-if="canManage && currentPhoto"
      class="lb-btn"
      :title="t('photos.myShares.shareFolder')"
      :disabled="creatingFolderShare"
      @click="$emit('open-folder-share-modal')"
    >
      📂
    </button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NDropdown, type DropdownOption } from 'naive-ui'
import { originalUrl, type Photo } from '@/api/photos'

defineProps<{
  zoom: number
  slideshowActive: boolean
  slideshowOptions: DropdownOption[]
  currentPhoto: Photo | null
  canUpload: boolean
  canManage: boolean
  creatingShare: boolean
  creatingFolderShare: boolean
}>()

defineEmits<{
  (e: 'zoom-out'): void
  (e: 'zoom-in'): void
  (e: 'rotate-left'): void
  (e: 'rotate-right'): void
  (e: 'reset-view'): void
  (e: 'select-slideshow', key: string): void
  (e: 'copy-link'): void
  (e: 'open-share-modal'): void
  (e: 'open-folder-share-modal'): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.lightbox__toolbar {
  position: absolute; top: 16px; left: 50%; transform: translateX(-50%);
  display: flex; align-items: center; gap: 6px;
  background: rgba(0,0,0,0.55); padding: 6px 10px; border-radius: 999px; z-index: 3;
}
.lb-btn {
  background: rgba(255,255,255,0.12); color: #fff; border: 0; cursor: pointer;
  width: 36px; height: 36px; border-radius: 50%; font-size: 16px;
  display: inline-flex; align-items: center; justify-content: center;
  text-decoration: none;
}
.lb-btn[disabled] { opacity: 0.5; cursor: not-allowed; }
.lb-btn:hover { background: rgba(255,255,255,0.22); }
.lb-btn--active { background: rgba(59,130,246,0.5); }
.lb-btn--active:hover { background: rgba(59,130,246,0.7); }
.lb-zoom { color: #fff; font-size: 12px; min-width: 44px; text-align: center; }
</style>
