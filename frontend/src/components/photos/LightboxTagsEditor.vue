<template>
  <div
    class="lightbox__tags-row"
    @click.stop
  >
    <template v-if="!editing">
      <n-tag
        v-for="tag in currentPhotoTags"
        :key="tag.id"
        size="small"
        class="lightbox__tag"
      >
        {{ tag.name }}
      </n-tag>
      <button
        v-if="canUpload"
        class="lightbox__tags-edit-btn"
        @click="$emit('start-edit')"
      >
        {{ currentPhotoTags.length ? '✎' : t('photos.tags.addTags') }}
      </button>
    </template>
    <template v-else>
      <n-select
        :value="editingTagIds"
        multiple
        filterable
        :options="tagOptions"
        size="small"
        style="min-width: 200px; max-width: 400px"
        :placeholder="t('photos.tags.addTags')"
        @update:value="$emit('update:editingTagIds', $event)"
      />
      <n-button
        size="tiny"
        type="primary"
        :loading="saving"
        @click="$emit('save')"
      >
        {{ t('photos.tags.saveTags') }}
      </n-button>
      <n-button
        size="tiny"
        @click="$emit('update:editing', false)"
      >
        {{ t('common.cancel') }}
      </n-button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NButton, NSelect, NTag, type SelectOption } from 'naive-ui'
import type { PhotoTag } from '@/api/photos'

defineProps<{
  editing: boolean
  currentPhotoTags: PhotoTag[]
  canUpload: boolean
  tagOptions: SelectOption[]
  editingTagIds: string[]
  saving: boolean
}>()

defineEmits<{
  (e: 'update:editing', val: boolean): void
  (e: 'update:editingTagIds', val: string[]): void
  (e: 'start-edit'): void
  (e: 'save'): void
}>()

const { t } = useI18n()
</script>

<style scoped>
.lightbox__tags-row {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 4px;
}
.lightbox__tag { margin: 0; }
.lightbox__tags-edit-btn {
  background: transparent; border: 0; cursor: pointer; font-size: 12px;
  color: rgba(255,255,255,0.6); padding: 0;
}
.lightbox__tags-edit-btn:hover { color: #fff; }
</style>
