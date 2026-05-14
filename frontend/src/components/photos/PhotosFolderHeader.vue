<template>
  <header class="photos-header">
    <div class="photos-header__info">
      <h1 class="photos-title">{{ folder.name }}</h1>

      <div v-if="editingDescription" class="desc-edit">
        <n-input
          :value="editDescValue"
          type="textarea"
          :rows="2"
          :placeholder="t('photos.folders.description')"
          @update:value="$emit('update:editDescValue', $event)"
        />
        <div class="desc-edit__actions">
          <n-button size="small" type="primary" @click="$emit('save-description')">{{ t('common.save') }}</n-button>
          <n-button size="small" @click="$emit('cancel-description')">{{ t('common.cancel') }}</n-button>
        </div>
      </div>
      <template v-else>
        <p v-if="folder.description" class="photos-desc">{{ folder.description }}</p>
        <button
          v-else-if="canManage"
          class="photos-add-desc"
          @click="$emit('start-edit-description')"
        >+ {{ t('photos.folders.addDescription') }}</button>
      </template>

      <p class="photos-meta">{{ t('photos.count', { n: folder.photos_count }) }}</p>
    </div>
    <div class="photos-actions">
      <n-select
        :value="sortBy"
        :options="sortOptions"
        style="width: 160px"
        @update:value="$emit('update:sortBy', $event)"
      />
      <n-button v-if="canUpload" @click="$emit('toggle-select-mode')">
        {{ selectMode ? t('photos.select.cancel') : t('photos.select.mode') }}
      </n-button>
      <n-button v-if="canUpload" type="primary" @click="$emit('trigger-upload')">
        + {{ t('photos.upload.button') }}
      </n-button>
      <n-button v-if="canManage" @click="$emit('open-permissions')">
        {{ t('photos.permissions.manage') }}
      </n-button>
      <n-button @click="$emit('start-zip')">
        ⬇ {{ t('photos.zip.download') }}
      </n-button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NSelect } from 'naive-ui'
import type { PhotoFolder } from '@/api/photos'

type SortBy = 'created_at' | 'taken_at' | 'original_name'

defineProps<{
  folder: PhotoFolder
  editingDescription: boolean
  editDescValue: string
  canManage: boolean
  canUpload: boolean
  selectMode: boolean
  sortBy: SortBy
}>()

defineEmits<{
  'update:editDescValue': [value: string]
  'update:sortBy': [value: SortBy]
  'start-edit-description': []
  'save-description': []
  'cancel-description': []
  'toggle-select-mode': []
  'trigger-upload': []
  'open-permissions': []
  'start-zip': []
}>()

const { t } = useI18n()

const sortOptions = computed(() => [
  { label: t('photos.sort.createdAt'), value: 'created_at' },
  { label: t('photos.sort.takenAt'), value: 'taken_at' },
  { label: t('photos.sort.name'), value: 'original_name' },
])
</script>

<style scoped>
.photos-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 20px; gap: 16px;
}
.photos-header__info { flex: 1; min-width: 0; }
.photos-title { margin: 0 0 4px; font-size: 22px; }
.photos-desc { margin: 0 0 4px; color: var(--color-text-muted); }
.photos-meta { margin: 0; font-size: 12px; color: var(--color-text-muted); }
.photos-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-start; }
.photos-add-desc {
  background: transparent; border: 0; cursor: pointer;
  font-size: 13px; color: var(--color-text-muted); padding: 0; margin: 0 0 4px;
  text-decoration: underline dashed;
}
.photos-add-desc:hover { color: var(--color-text); }

.desc-edit { margin-bottom: 8px; }
.desc-edit__actions { display: flex; gap: 8px; margin-top: 8px; }
</style>
