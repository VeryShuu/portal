<template>
  <AppLayout>
    <template #header-title><span>{{ t('bookmarks.title') }}</span></template>

    <div class="bookmarks-wrap">
      <div class="bookmarks-header">
        <n-button type="primary" @click="showAdd = true">+ {{ t('bookmarks.add') }}</n-button>
      </div>

      <n-spin v-if="store.loadingBookmarks" style="margin-top: 40px" />

      <template v-else>
        <n-empty v-if="!store.bookmarks.length" :description="t('bookmarks.empty')" style="margin-top: 60px" />

        <div v-else class="bookmark-list">
          <div
            v-for="(bm, index) in store.bookmarks"
            :key="bm.id"
            class="bookmark-item"
            :class="{ 'drag-over': dragOverIndex === index }"
            draggable="true"
            @dragstart="onDragStart(index)"
            @dragover.prevent="onDragOver(index)"
            @dragleave="onDragLeave"
            @drop.prevent="onDrop(index)"
            @dragend="onDragEnd"
          >
            <n-icon class="drag-handle" size="18"><ReorderTwoOutline /></n-icon>
            <div class="bm-group" v-if="bm.group_name">
              <n-tag size="tiny" :bordered="false">{{ bm.group_name }}</n-tag>
            </div>
            <a :href="bm.url" target="_blank" rel="noopener" class="bm-link">{{ bm.title }}</a>
            <span class="bm-url">{{ bm.url }}</span>
            <n-button
              size="tiny"
              quaternary
              circle
              class="bm-del"
              @click="removeBookmark(bm.id)"
            >
              <template #icon><n-icon><TrashOutline /></n-icon></template>
            </n-button>
          </div>
        </div>
      </template>
    </div>

    <n-modal v-model:show="showAdd" preset="dialog" :title="t('bookmarks.add')">
      <n-form @submit.prevent="submitAdd">
        <n-form-item :label="t('bookmarks.titleField')">
          <n-input v-model:value="newTitle" :placeholder="t('bookmarks.titlePlaceholder')" />
        </n-form-item>
        <n-form-item label="URL">
          <n-input v-model:value="newUrl" placeholder="https://..." />
        </n-form-item>
        <n-form-item :label="t('bookmarks.groupLabel')">
          <n-input v-model:value="newGroup" :placeholder="t('bookmarks.groupPlaceholder')" />
        </n-form-item>
      </n-form>
      <template #action>
        <n-button @click="showAdd = false">{{ t('common.cancel') }}</n-button>
        <n-button type="primary" :disabled="!newTitle || !newUrl" @click="submitAdd">
          {{ t('common.save') }}
        </n-button>
      </template>
    </n-modal>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NSpin, NEmpty, NIcon, NModal, NForm, NFormItem, NInput, NTag,
} from 'naive-ui'
import { ReorderTwoOutline, TrashOutline } from '@vicons/ionicons5'
import AppLayout from '../components/AppLayout.vue'
import { useLinksStore } from '../stores/links'

const { t } = useI18n()
const store = useLinksStore()

onMounted(() => store.loadBookmarks())

const showAdd = ref(false)
const newTitle = ref('')
const newUrl = ref('')
const newGroup = ref('')

async function submitAdd() {
  if (!newTitle.value || !newUrl.value) return
  await store.addBookmark({
    title: newTitle.value,
    url: newUrl.value,
    group_name: newGroup.value || null,
  })
  newTitle.value = ''
  newUrl.value = ''
  newGroup.value = ''
  showAdd.value = false
}

async function removeBookmark(id: string) {
  await store.removeBookmark(id)
}

const dragIndex = ref<number | null>(null)
const dragOverIndex = ref<number | null>(null)

function onDragStart(index: number) {
  dragIndex.value = index
}

function onDragOver(index: number) {
  if (dragIndex.value !== null && dragIndex.value !== index) {
    dragOverIndex.value = index
  }
}

function onDragLeave() {
  dragOverIndex.value = null
}

async function onDrop(dropIndex: number) {
  if (dragIndex.value === null || dragIndex.value === dropIndex) return

  const items = [...store.bookmarks]
  const [moved] = items.splice(dragIndex.value, 1)
  items.splice(dropIndex, 0, moved)

  const reorderPayload = items.map((bm, i) => ({ id: bm.id, sort_order: i }))
  await store.reorder(reorderPayload)

  dragOverIndex.value = null
  dragIndex.value = null
}

function onDragEnd() {
  dragIndex.value = null
  dragOverIndex.value = null
}
</script>

<style scoped>
.bookmarks-wrap {
  max-width: 720px;
  margin: 0 auto;
}
.bookmarks-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 20px;
}
.bookmark-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.bookmark-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid var(--n-border-color, #e0e0e0);
  background: var(--n-card-color, #fff);
  cursor: default;
  transition: box-shadow 0.15s, border-color 0.15s;
  user-select: none;
}
.bookmark-item:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.bookmark-item.drag-over {
  border-color: var(--n-primary-color, #18a058);
  box-shadow: 0 0 0 2px rgba(24, 160, 88, 0.25);
}
.drag-handle {
  cursor: grab;
  color: var(--n-text-color-3, #aaa);
  flex-shrink: 0;
}
.drag-handle:active {
  cursor: grabbing;
}
.bm-group {
  flex-shrink: 0;
}
.bm-link {
  font-weight: 600;
  text-decoration: none;
  color: var(--n-text-color, inherit);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
  flex-shrink: 0;
}
.bm-link:hover {
  text-decoration: underline;
  color: var(--n-primary-color, #18a058);
}
.bm-url {
  flex: 1;
  font-size: 12px;
  color: var(--n-text-color-3, #aaa);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bm-del {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}
.bookmark-item:hover .bm-del {
  opacity: 1;
}
</style>
