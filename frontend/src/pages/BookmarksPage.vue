<template>
  <div class="bookmarks-wrap">
      <header class="page-head">
        <div>
          <h1 class="page-head__title">{{ t('bookmarks.title') }}</h1>
          <p class="page-head__sub">{{ t('bookmarks.pageSub') }}</p>
        </div>
        <n-button type="primary" size="medium" @click="showAdd = true">
          <template #icon><n-icon><AddOutline /></n-icon></template>
          {{ t('bookmarks.add') }}
        </n-button>
      </header>

      <n-spin v-if="store.loadingBookmarks" style="margin:60px auto;display:block" />

      <template v-else>
        <EmptyState
          v-if="!store.bookmarks.length"
          variant="bookmark"
          :title="t('bookmarks.empty')"
          :description="t('bookmarks.emptyHint')"
        />

        <div v-else class="bookmark-grid">
          <div
            v-for="(bm, index) in store.bookmarks"
            :key="bm.id"
            class="bookmark-card"
            :class="{ 'drag-over': dragOverIndex === index }"
            draggable="true"
            @dragstart="onDragStart(index)"
            @dragover.prevent="onDragOver(index)"
            @dragleave="onDragLeave"
            @drop.prevent="onDrop(index)"
            @dragend="onDragEnd"
          >
            <div class="bc-top">
              <div class="bc-favicon" :style="{ background: colorFor(bm.url) }">
                <img
                  v-if="faviconFor(bm.url)"
                  :src="faviconFor(bm.url)!"
                  :alt="bm.title"
                  @error="onFaviconError($event)"
                />
                <n-icon v-else size="18"><LinkOutline /></n-icon>
              </div>
              <button
                type="button"
                class="bc-drag"
                :aria-label="t('bookmarks.reorder')"
                tabindex="-1"
              >
                <n-icon size="16"><ReorderTwoOutline /></n-icon>
              </button>
              <n-button
                size="tiny"
                quaternary
                circle
                class="bc-del"
                :aria-label="t('bookmarks.remove')"
                @click="removeBookmark(bm.id)"
              >
                <template #icon><n-icon><TrashOutline /></n-icon></template>
              </n-button>
            </div>

            <a :href="bm.url" target="_blank" rel="noopener" class="bc-link">
              <div class="bc-title">{{ bm.title }}</div>
              <div class="bc-url">{{ shortUrl(bm.url) }}</div>
            </a>

            <div v-if="bm.group_name" class="bc-group">
              <n-tag size="tiny" :bordered="false" round>{{ bm.group_name }}</n-tag>
            </div>
          </div>
        </div>
      </template>

    <n-modal v-model:show="showAdd" preset="dialog" :title="t('bookmarks.add')" style="max-width: 480px">
      <n-form @submit.prevent="submitAdd" label-placement="top">
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton, NSpin, NIcon, NModal, NForm, NFormItem, NInput, NTag, useMessage,
} from 'naive-ui'
import { ReorderTwoOutline, TrashOutline, LinkOutline, AddOutline } from '@vicons/ionicons5'
import EmptyState from '../components/EmptyState.vue'
import { useLinksStore } from '../stores/links'
import { isSafeHttpUrl } from '../utils/url'

const { t } = useI18n()
const store = useLinksStore()
const message = useMessage()

onMounted(() => store.loadBookmarks())

const showAdd = ref(false)
const newTitle = ref('')
const newUrl = ref('')
const newGroup = ref('')

async function submitAdd() {
  if (!newTitle.value || !newUrl.value) return
  if (!isSafeHttpUrl(newUrl.value)) {
    message.error(t('admin.links.form.invalidUrl'))
    return
  }
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

function faviconFor(url: string): string | null {
  try {
    const u = new URL(url)
    return `${u.origin}/favicon.ico`
  } catch {
    return null
  }
}

function shortUrl(url: string): string {
  try {
    const u = new URL(url)
    return u.hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

const palette = [
  '#e0eafc', '#ffe4e1', '#ede4ff', '#dcfce7', '#fef3c7', '#e0f2fe', '#fce7f3',
]
function colorFor(url: string): string {
  let hash = 0
  for (let i = 0; i < url.length; i++) hash = (hash * 31 + url.charCodeAt(i)) >>> 0
  return palette[hash % palette.length]
}

function onFaviconError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
}

const dragIndex = ref<number | null>(null)
const dragOverIndex = ref<number | null>(null)

function onDragStart(index: number) { dragIndex.value = index }
function onDragOver(index: number) {
  if (dragIndex.value !== null && dragIndex.value !== index) {
    dragOverIndex.value = index
  }
}
function onDragLeave() { dragOverIndex.value = null }

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
  max-width: 1200px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}
.page-head__title {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-text);
}
.page-head__sub {
  margin: 4px 0 0;
  color: var(--color-text-muted);
  font-size: 14px;
}

.bookmark-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}

.bookmark-card {
  position: relative;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 14px 16px 16px;
  box-shadow: var(--shadow-sm);
  transition: transform var(--t-base), box-shadow var(--t-base), border-color var(--t-base);
  cursor: grab;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 130px;
}
.bookmark-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--color-brand-sky);
}
.bookmark-card.drag-over {
  border-color: var(--color-brand-red);
  box-shadow: 0 0 0 2px rgba(216, 38, 44, 0.2), var(--shadow-md);
}
.bookmark-card:active { cursor: grabbing; }

.bc-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.bc-favicon {
  width: 34px;
  height: 34px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  color: var(--color-brand-navy);
  flex-shrink: 0;
}
.bc-favicon img {
  width: 20px;
  height: 20px;
  object-fit: contain;
}
.bc-drag {
  margin-left: auto;
  background: transparent;
  border: none;
  color: var(--color-text-subtle);
  cursor: grab;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
}
.bc-del {
  opacity: 0;
  transition: opacity var(--t-fast);
}
.bookmark-card:hover .bc-del { opacity: 1; }

.bc-link {
  display: block;
  text-decoration: none;
  color: inherit;
  flex: 1;
  min-width: 0;
}
.bc-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.35;
  margin-bottom: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.bc-link:hover .bc-title { color: var(--color-brand-red); }
.bc-url {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.bc-group {
  display: flex;
}

@media (max-width: 640px) {
  .page-head { flex-direction: column; align-items: stretch; }
  .bookmark-grid { grid-template-columns: 1fr 1fr; gap: 10px; }
}
</style>
