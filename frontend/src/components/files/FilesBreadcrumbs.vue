<template>
  <nav
    v-if="breadcrumbs.length"
    class="files-breadcrumbs"
  >
    <span
      v-for="crumb in breadcrumbs"
      :key="crumb.id"
      class="files-breadcrumb"
    >
      <span
        class="files-breadcrumb__link"
        role="button"
        tabindex="0"
        @click="$emit('select', crumb.id)"
        @keydown.enter="$emit('select', crumb.id)"
      >{{ crumb.name }}</span>
      <span class="files-breadcrumb__sep">/</span>
    </span>
    <span class="files-breadcrumb files-breadcrumb--current">{{ current?.name }}</span>
  </nav>
</template>

<script setup lang="ts">
import type { FileFolderPublic } from '../../api/files'

defineProps<{
  breadcrumbs: FileFolderPublic[]
  current: FileFolderPublic | null
}>()

defineEmits<{
  select: [id: string]
}>()
</script>

<style scoped>
.files-breadcrumbs {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  margin-bottom: 12px;
  color: var(--n-text-color-3, #666);
}

.files-breadcrumb__link {
  cursor: pointer;
  color: var(--n-primary-color, #18a058);
}

.files-breadcrumb__link:hover {
  text-decoration: underline;
}

.files-breadcrumb__sep {
  margin: 0 2px;
}

.files-breadcrumb--current {
  font-weight: 600;
  color: var(--n-text-color, #333);
}
</style>
