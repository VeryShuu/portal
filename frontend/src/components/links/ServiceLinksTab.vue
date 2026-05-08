<template>
  <div>
    <n-spin v-if="store.loadingLinks" style="margin:60px auto;display:block" />
    <template v-else>
      <EmptyState
        v-if="!Object.keys(groupedItems).length"
        variant="default"
        :title="t('links.empty')"
        :description="t('links.emptyHint')"
      />
      <template v-for="(items, group) in groupedItems" :key="`corporate::${group}`">
        <section class="category-section">
          <h3 v-if="shouldShowGroupTitle(group as string)" class="category-title">{{ group }}</h3>
          <div
            class="links-grid"
            :ref="(el) => bindSortable(el as Element | null, group as string)"
          >
            <LinkCard
              v-for="item in items"
              :key="item.id"
              :item="item"
              :canDrag="auth.isAdmin"
              :isAdmin="auth.isAdmin"
              @edit="openEditLink"
              @delete="handleDelete"
            />
          </div>
        </section>
      </template>
    </template>

    <LinkFormModal
      v-if="auth.isAdmin"
      v-model:show="modalOpen"
      :editingLink="editingLink"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NSpin, useMessage } from 'naive-ui'
import { useConfirmDialog } from '../../composables/useConfirmDialog'
import { useSortableGroups } from '../../composables/useSortableGroups'
import { useLinksStore } from '../../stores/links'
import { useAuthStore } from '../../stores/auth'
import { deleteLink, type ServiceLink, type NormalizedItem } from '../../api/links'
import EmptyState from '../EmptyState.vue'
import LinkCard from './LinkCard.vue'
import LinkFormModal from './LinkFormModal.vue'
import { ref } from 'vue'

const { t } = useI18n()
const store = useLinksStore()
const auth = useAuthStore()
const message = useMessage()
const { confirm } = useConfirmDialog()

const modalOpen = ref(false)
const editingLink = ref<ServiceLink | null>(null)

const otherGroupLabel = computed(() => t('links.other'))

const normalizedItems = computed<NormalizedItem[]>(() =>
  store.links.map((l) => ({
    id: l.id,
    title: l.title,
    url: l.url,
    description: l.description,
    iconUrl: l.icon_url,
    supportsSso: l.supports_sso,
    group: l.category || otherGroupLabel.value,
    kind: 'link' as const,
    raw: l,
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

const canDrag = computed(() => auth.isAdmin)

function shouldShowGroupTitle(group: string): boolean {
  if (group === otherGroupLabel.value) return false
  return Object.keys(groupedItems.value).length > 1
}

const { bindSortable } = useSortableGroups(canDrag, reorderLinksInGroup)

async function reorderLinksInGroup(group: string, fromIdx: number, toIdx: number) {
  const slots: number[] = []
  store.links.forEach((l, i) => {
    if ((l.category || otherGroupLabel.value) === group) slots.push(i)
  })
  const newGroupOrder = slots.map((i) => store.links[i])
  const [moved] = newGroupOrder.splice(fromIdx, 1)
  newGroupOrder.splice(toIdx, 0, moved)

  const newFlat = [...store.links]
  slots.forEach((slot, i) => { newFlat[slot] = newGroupOrder[i] })

  store.setLinks(newFlat)
  const payload = newFlat.map((l, i) => ({ id: l.id, sort_order: i }))
  try {
    await store.reorderLinks(payload)
  } catch {
    message.error(t('errors.generic'))
    await store.loadLinks()
  }
}

function openAdd() {
  editingLink.value = null
  modalOpen.value = true
}

function openEditLink(item: NormalizedItem) {
  editingLink.value = item.raw as ServiceLink
  modalOpen.value = true
}

async function handleDelete(item: NormalizedItem) {
  const link = item.raw as ServiceLink
  const ok = await confirm({
    title: t('admin.links.confirmDelete', { title: link.title }),
    content: t('admin.links.confirmDeleteHint'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
  })
  if (!ok) return
  try {
    await deleteLink(link.id)
    store.removeLink(link.id)
    message.success(t('admin.links.deleted'))
  } catch {
    message.error(t('errors.generic'))
  }
}

onMounted(() => { store.loadLinks() })

watch(() => store.errorLinks, (val) => {
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
