<template>
  <div class="toolbar">
    <TextFormattingGroup :editor="editor" />
    <HeadingsGroup :editor="editor" />
    <ListsGroup :editor="editor" />
    <MediaGroup
      :editor="editor"
      @open-link="emit('open-link')"
      @insert-image="emit('insert-image')"
      @open-video="emit('open-video')"
      @open-details="emit('open-details')"
    />
    <HistoryGroup
      :editor="editor"
      :fullscreen="fullscreen"
      :focus-mode="focusMode"
      @toggle-fullscreen="emit('toggle-fullscreen')"
      @toggle-focus="emit('toggle-focus')"
    />
  </div>
</template>

<script setup lang="ts">
import type { Editor } from '@tiptap/vue-3'
import TextFormattingGroup from './groups/TextFormattingGroup.vue'
import HeadingsGroup from './groups/HeadingsGroup.vue'
import ListsGroup from './groups/ListsGroup.vue'
import MediaGroup from './groups/MediaGroup.vue'
import HistoryGroup from './groups/HistoryGroup.vue'

defineProps<{
  editor: Editor
  fullscreen?: boolean
  focusMode?: boolean
}>()

const emit = defineEmits<{
  'open-link': []
  'insert-image': []
  'open-video': []
  'open-details': []
  'toggle-fullscreen': []
  'toggle-focus': []
}>()
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  padding: 8px 10px;
  border-bottom: 1px solid var(--n-border-color, #e0e0e6);
  background: var(--n-color, #fff);
  flex: 0 0 auto;
}
</style>
