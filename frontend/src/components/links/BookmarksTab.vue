<template>
  <div>
    <n-spin
      v-if="store.loadingBookmarks"
      style="margin:60px auto;display:block"
    />
    <template v-else>
      <EmptyState
        v-if="!Object.keys(groupedItems).length"
        variant="bookmark"
        :title="t('bookmarks.empty')"
        :description="t('bookmarks.emptyHint')"
      />
      <template
        v-for="(items, group) in groupedItems"
        :key="`my::${group}`"
      >
        <section class="category-section">
          <h3
            v-if="shouldShowGroupTitle(group as string)"
            class="category-title"
          >
            {{ group }}
          </h3>
          <div
            :ref="(el) => bindSortable(el as Element | null, group as string)"
            class="links-grid"
          >
            <LinkCard
              v-for="item in items"
              :key="item.id"
              :item="item"
              :can-drag="true"
              :is-admin="false"
              @delete="handleDelete"
            />
          </div>
        </section>
      </template>
    </template>

    <BookmarkFormModal v-model:show="modalOpen" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NSpin, useMessage } from 'naive-ui'
import { useSortableGroups } from '../../composables/useSortableGroups'
import { useLinksStore } from '../../stores/links'
import type { NormalizedItem } from '../../api/links'
import EmptyState from '../EmptyState.vue'
import LinkCard from './LinkCard.vue'
import BookmarkFormModal from './BookmarkFormModal.vue'
import { ref } from 'vue'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const store = useLinksStore()
const message = useMessage()

const modalOpen = ref(false)

const otherGroupLabel = computed(() => t('links.other'))

const normalizedItems = computed<NormalizedItem[]>(() =>
  store.bookmarks.map((b) => ({
    id: b.id,
    title: b.title,
    url: b.url,
    description: null,
    iconUrl: null,
    supportsSso: false,
    group: b.group_name || otherGroupLabel.value,
    kind: 'bookmark' as const,
    raw: b,
  })),
)

const groupedItems = computed<Record<string, NormalizedItem[]>>(() => {
  const groups: Record<string, NormalizedItem[]> = {}
  for (const item of normalizedItems.value) {
    if (!groups[item.group]) groups[item.group] = []
    groups[item.group].push(item)
  }
  return groups
})

const canDrag = computed(() => true)

function shouldShowGroupTitle(group: string): boolean {
  if (group === otherGroupLabel.value) return false
  return Object.keys(groupedItems.value).length > 1
}

const { bindSortable } = useSortableGroups(canDrag, reorderBookmarksInGroup)

async function reorderBookmarksInGroup(group: string, fromIdx: number, toIdx: number) {
  const slots: number[] = []
  store.bookmarks.forEach((bm, i) => {
    if ((bm.group_name || otherGroupLabel.value) === group) slots.push(i)
  })
  const newGroupOrder = slots.map((i) => store.bookmarks[i])
  const [moved] = newGroupOrder.splice(fromIdx, 1)
  newGroupOrder.splice(toIdx, 0, moved)

  const newFlat = [...store.bookmarks]
  slots.forEach((slot, i) => { newFlat[slot] = newGroupOrder[i] })

  const payload = newFlat.map((bm, i) => ({ id: bm.id, sort_order: i }))
  try {
    await store.reorder(payload)
  } catch (e) {
    message.error(parseApiError(e, t))
    await store.loadBookmarks()
  }
}

async function handleDelete(item: NormalizedItem) {
  await store.removeBookmark(item.id)
}

function openAdd() {
  modalOpen.value = true
}

onMounted(() => { store.loadBookmarks() })

watch(() => store.errorBookmarks, (val) => {
  if (val) message.error(t('errors.generic'))
})

defineExpose({ openAdd })
</script>

<style scoped>
.category-section {
  margin-bottom: 32px;
}
.category-title {
  font-size: 11px;
  font-weight: 700;
  margin: 0 0 14px;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.links-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
</style>
