<template>
  <div class="links-wrap">
    <header class="page-head">
      <div>
        <h1 class="page-head__title">{{ t('nav.links') }}</h1>
        <p class="page-head__sub">{{ t('links.pageSub') }}</p>
      </div>
      <n-button
        v-if="activeTab === 'corporate' && auth.isAdmin"
        type="primary"
        @click="openAddLink"
      >
        <template #icon><n-icon><AddOutline /></n-icon></template>
        {{ t('admin.links.add') }}
      </n-button>
      <n-button
        v-else-if="activeTab === 'my'"
        type="primary"
        @click="showAdd = true"
      >
        <template #icon><n-icon><AddOutline /></n-icon></template>
        {{ t('bookmarks.add') }}
      </n-button>
    </header>

    <n-tabs
      :value="activeTab"
      type="line"
      animated
      style="margin-bottom: 24px"
      @update:value="setTab"
    >
      <n-tab name="corporate">{{ t('links.tabs.corporate') }}</n-tab>
      <n-tab name="my">{{ t('links.tabs.my') }}</n-tab>
    </n-tabs>

    <!-- ── UNIFIED CONTENT ── -->
    <n-spin
      v-if="(activeTab === 'corporate' && store.loadingLinks) || (activeTab === 'my' && store.loadingBookmarks)"
      style="margin:60px auto;display:block"
    />
    <template v-else>
      <EmptyState
        v-if="!Object.keys(groupedItems).length"
        :variant="activeTab === 'my' ? 'bookmark' : 'default'"
        :title="activeTab === 'my' ? t('bookmarks.empty') : t('links.empty')"
        :description="activeTab === 'my' ? t('bookmarks.emptyHint') : t('links.emptyHint')"
      />

      <template v-for="(items, group) in groupedItems" :key="`${activeTab}::${group}`">
        <section class="category-section">
          <h3 v-if="shouldShowGroupTitle(group)" class="category-title">{{ group }}</h3>
          <div
            class="links-grid"
            :ref="(el) => bindSortable(el as Element | null, group)"
          >
            <div
              v-for="item in items"
              :key="item.id"
              class="link-card-wrap"
              :class="{ 'link-card-wrap--draggable': canDrag }"
              :data-id="item.id"
            >
              <a
                :href="hrefFor(item)"
                target="_blank"
                rel="noopener noreferrer"
                class="link-card"
                :draggable="false"
              >
                <span
                  v-if="canDrag"
                  class="drag-handle"
                  :title="t('common.dragToReorder')"
                  :aria-label="t('common.dragToReorder')"
                  @click.prevent.stop
                >
                  <n-icon size="16"><ReorderTwoOutline /></n-icon>
                </span>
                <div class="link-icon" :style="{ background: colorFor(item.url) }">
                  <img
                    v-if="item.iconUrl"
                    :src="item.iconUrl"
                    :alt="item.title"
                    @error="onIconError($event)"
                  />
                  <img
                    v-else-if="faviconFor(item.url)"
                    :src="faviconFor(item.url)!"
                    :alt="item.title"
                    @error="onIconError($event)"
                  />
                  <n-icon v-else size="22"><LinkOutline /></n-icon>
                </div>
                <div class="link-info">
                  <div class="link-title">
                    {{ item.title }}
                    <span v-if="item.supportsSso" class="sso-badge" :title="t('links.sso')">
                      <n-icon size="12"><ShieldCheckmarkOutline /></n-icon>
                      SSO
                    </span>
                  </div>
                  <div v-if="item.description" class="link-desc">{{ item.description }}</div>
                  <div class="link-url">{{ shortUrl(item.url) }}</div>
                </div>
                <n-icon class="link-arrow" size="16"><OpenOutline /></n-icon>
              </a>
              <div v-if="hasActions(item)" class="link-admin-actions">
                <n-button
                  v-if="item.kind === 'link' && auth.isAdmin"
                  size="tiny"
                  quaternary
                  circle
                  :title="t('common.edit')"
                  :aria-label="t('common.edit')"
                  @click.prevent.stop="openEditLink(item.raw as ServiceLink)"
                >
                  <template #icon><n-icon size="13"><CreateOutline /></n-icon></template>
                </n-button>
                <n-button
                  size="tiny"
                  quaternary
                  circle
                  type="error"
                  :title="item.kind === 'bookmark' ? t('bookmarks.remove') : t('common.delete')"
                  :aria-label="item.kind === 'bookmark' ? t('bookmarks.remove') : t('common.delete')"
                  @click.prevent.stop="handleDelete(item)"
                >
                  <template #icon><n-icon size="13"><TrashOutline /></n-icon></template>
                </n-button>
              </div>
            </div>
          </div>
        </section>
      </template>
    </template>

    <!-- ── LINK FORM MODAL (admin) ── -->
    <n-modal
      v-if="auth.isAdmin"
      v-model:show="linkModalOpen"
      :title="editingLink ? t('admin.links.editTitle') : t('admin.links.addTitle')"
      preset="card"
      style="width:540px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form :model="linkForm" :rules="linkRules" ref="linkFormRef" label-placement="top">
        <div class="modal-form-row">
          <n-form-item :label="t('admin.links.form.titleLabel')" path="title">
            <n-input v-model:value="linkForm.title" :placeholder="t('admin.links.form.titlePlaceholder')" />
          </n-form-item>
          <n-form-item :label="t('admin.links.form.urlLabel')" path="url">
            <n-input v-model:value="linkForm.url" :placeholder="t('admin.links.form.urlPlaceholder')" />
          </n-form-item>
        </div>
        <div class="modal-form-row">
          <n-form-item :label="t('admin.links.form.categoryLabel')">
            <n-input v-model:value="linkForm.category" :placeholder="t('admin.links.form.categoryPlaceholder')" clearable />
          </n-form-item>
          <n-form-item :label="t('admin.links.form.sortOrderLabel')">
            <n-input-number v-model:value="linkForm.sort_order" :min="0" style="width:100%" />
          </n-form-item>
        </div>
        <n-form-item :label="t('admin.links.form.descriptionLabel')">
          <n-input
            v-model:value="linkForm.description"
            type="textarea"
            :rows="2"
            :placeholder="t('admin.links.form.descriptionPlaceholder')"
            clearable
          />
        </n-form-item>
        <n-form-item :label="t('admin.links.form.iconLabel')">
          <div class="icon-upload-row">
            <div v-if="iconPreview || (editingLink && editingLink.icon_url)" class="icon-preview-wrap">
              <img :src="iconPreview || editingLink!.icon_url!" class="icon-preview" alt="" />
              <n-button size="tiny" circle quaternary type="error" class="icon-preview-remove" @click="removeIcon">×</n-button>
            </div>
            <n-upload
              accept="image/png,image/jpeg,image/webp,image/svg+xml,image/x-icon"
              :max="1"
              :show-file-list="false"
              @change="onIconFileChange"
            >
              <n-button size="small">{{ t('admin.links.form.iconUploadBtn') }}</n-button>
            </n-upload>
          </div>
        </n-form-item>
        <div class="modal-form-checks">
          <n-checkbox v-model:checked="linkForm.supports_sso">{{ t('admin.links.form.supportsSSO') }}</n-checkbox>
          <n-checkbox v-model:checked="linkForm.is_active">{{ t('admin.links.form.isActive') }}</n-checkbox>
        </div>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="linkModalOpen = false">{{ t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="savingLink" @click="submitLink">{{ t('common.save') }}</n-button>
        </div>
      </template>
    </n-modal>

    <!-- ── DELETE LINK CONFIRM (admin) ── -->
    <n-modal
      v-if="auth.isAdmin"
      v-model:show="deleteConfirmOpen"
      :title="t('admin.links.confirmDelete', { title: deletingLink?.title ?? '' })"
      preset="dialog"
      type="warning"
      :positive-text="t('common.delete')"
      :negative-text="t('common.cancel')"
      @positive-click="confirmDelete"
    >
      {{ t('admin.links.confirmDeleteHint') }}
    </n-modal>

    <!-- ── ADD BOOKMARK MODAL ── -->
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import Sortable from 'sortablejs'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NSpin, NIcon, NButton, NModal, NForm, NFormItem,
  NInput, NInputNumber, NCheckbox, NUpload, NTabs, NTab, useMessage,
  type UploadFileInfo,
} from 'naive-ui'
import {
  LinkOutline, ShieldCheckmarkOutline, OpenOutline, AddOutline,
  CreateOutline, TrashOutline, ReorderTwoOutline,
} from '@vicons/ionicons5'
import EmptyState from '../components/EmptyState.vue'
import { useLinksStore } from '../stores/links'
import { useAuthStore } from '../stores/auth'
import {
  createLink, updateLink, deleteLink, uploadLinkIcon, deleteLinkIcon,
  type ServiceLink, type CreateLinkDto, type Bookmark,
} from '../api/links'
import { BASE_URL } from '../api'
import { isSafeHttpUrl } from '../utils/url'

type NormalizedItem = {
  id: string
  title: string
  url: string
  description: string | null
  iconUrl: string | null
  supportsSso: boolean
  group: string
  kind: 'link' | 'bookmark'
  raw: ServiceLink | Bookmark
}

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const store = useLinksStore()
const auth = useAuthStore()
const message = useMessage()

const activeTab = computed(() =>
  (route.query.tab as string) === 'my' ? 'my' : 'corporate',
)

function setTab(val: string) {
  router.replace({ query: val === 'my' ? { tab: 'my' } : {} })
}

onMounted(() => {
  store.loadLinks()
  store.loadBookmarks()
})

// ── Corporate: icon state ──────────────────────────────────────────────────
const iconFile = ref<File | null>(null)
const iconPreview = ref<string | null>(null)
const iconRemoved = ref(false)

onUnmounted(() => {
  if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
})

function onIconFileChange({ file }: { file: UploadFileInfo }) {
  if (file.file) {
    if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
    iconFile.value = file.file
    iconPreview.value = URL.createObjectURL(file.file)
    iconRemoved.value = false
  }
}

function removeIcon() {
  if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
  iconFile.value = null
  iconPreview.value = null
  iconRemoved.value = true
}

function resetIconState() {
  if (iconPreview.value) URL.revokeObjectURL(iconPreview.value)
  iconFile.value = null
  iconPreview.value = null
  iconRemoved.value = false
}

// ── Corporate: link CRUD ───────────────────────────────────────────────────
const linkModalOpen = ref(false)
const savingLink = ref(false)
const editingLink = ref<ServiceLink | null>(null)
const linkFormRef = ref()
const deleteConfirmOpen = ref(false)
const deletingLink = ref<ServiceLink | null>(null)

const emptyLinkForm = () => ({
  title: '',
  url: '',
  description: null as string | null,
  category: null as string | null,
  sort_order: 0,
  supports_sso: false,
  is_active: true,
})
const linkForm = ref(emptyLinkForm())

const linkRules = computed(() => ({
  title: [{ required: true, message: t('admin.links.form.required'), trigger: 'blur' }],
  url: [
    { required: true, message: t('admin.links.form.required'), trigger: 'blur' },
    {
      validator: (_: unknown, value: string) => isSafeHttpUrl(value),
      message: t('admin.links.form.invalidUrl'),
      trigger: 'blur',
    },
  ],
}))

function openAddLink() {
  editingLink.value = null
  linkForm.value = emptyLinkForm()
  resetIconState()
  linkModalOpen.value = true
}

function openEditLink(link: ServiceLink) {
  editingLink.value = link
  linkForm.value = {
    title: link.title,
    url: link.url,
    description: link.description,
    category: link.category,
    sort_order: link.sort_order,
    supports_sso: link.supports_sso,
    is_active: link.is_active,
  }
  resetIconState()
  linkModalOpen.value = true
}

function openDeleteLink(link: ServiceLink) {
  deletingLink.value = link
  deleteConfirmOpen.value = true
}

async function submitLink() {
  try { await linkFormRef.value?.validate() } catch { return }
  savingLink.value = true
  try {
    const dto: CreateLinkDto = {
      title: linkForm.value.title,
      url: linkForm.value.url,
      description: linkForm.value.description || null,
      category: linkForm.value.category || null,
      sort_order: linkForm.value.sort_order ?? 0,
      supports_sso: linkForm.value.supports_sso,
      is_active: linkForm.value.is_active,
    }

    let saved: ServiceLink
    if (editingLink.value) {
      saved = await updateLink(editingLink.value.id, dto)
      const idx = store.links.findIndex(l => l.id === editingLink.value!.id)
      if (idx !== -1) store.links.splice(idx, 1, saved)
    } else {
      saved = await createLink(dto)
      store.links.splice(0, 0, saved)
    }

    if (iconFile.value) {
      const withIcon = await uploadLinkIcon(saved.id, iconFile.value)
      const idx = store.links.findIndex(l => l.id === saved.id)
      if (idx !== -1) store.links.splice(idx, 1, withIcon)
    } else if (iconRemoved.value && editingLink.value?.icon_url) {
      await deleteLinkIcon(saved.id)
      const idx = store.links.findIndex(l => l.id === saved.id)
      if (idx !== -1) store.links.splice(idx, 1, { ...store.links[idx], icon_url: null })
    }

    message.success(t('admin.links.saved'))
    linkModalOpen.value = false
  } catch {
    message.error(t('errors.generic'))
  } finally {
    savingLink.value = false
  }
}

async function confirmDelete() {
  if (!deletingLink.value) return
  try {
    await deleteLink(deletingLink.value.id)
    const idx = store.links.findIndex(l => l.id === deletingLink.value!.id)
    if (idx !== -1) store.links.splice(idx, 1)
    message.success(t('admin.links.deleted'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    deletingLink.value = null
  }
}

// ── My bookmarks: add/remove ───────────────────────────────────────────────
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

// ── Unified items + grouping ──────────────────────────────────────────────
const otherGroupLabel = computed(() => t('links.other'))

const normalizedItems = computed<NormalizedItem[]>(() => {
  if (activeTab.value === 'corporate') {
    return store.links.map((l) => ({
      id: l.id,
      title: l.title,
      url: l.url,
      description: l.description,
      iconUrl: l.icon_url,
      supportsSso: l.supports_sso,
      group: l.category || otherGroupLabel.value,
      kind: 'link',
      raw: l,
    }))
  }
  return store.bookmarks.map((b) => ({
    id: b.id,
    title: b.title,
    url: b.url,
    description: null,
    iconUrl: null,
    supportsSso: false,
    group: b.group_name || otherGroupLabel.value,
    kind: 'bookmark',
    raw: b,
  }))
})

const groupedItems = computed<Record<string, NormalizedItem[]>>(() => {
  const groups: Record<string, NormalizedItem[]> = {}
  for (const item of normalizedItems.value) {
    if (!groups[item.group]) groups[item.group] = []
    groups[item.group].push(item)
  }
  return groups
})

const canDrag = computed(() =>
  activeTab.value === 'my' || (activeTab.value === 'corporate' && auth.isAdmin),
)

function hrefFor(item: NormalizedItem): string {
  if (item.kind === 'link' && item.supportsSso) {
    return `${BASE_URL}/links/${item.id}/sso-redirect`
  }
  return item.url
}

function hasActions(item: NormalizedItem): boolean {
  if (item.kind === 'bookmark') return true
  return auth.isAdmin
}

function shouldShowGroupTitle(group: string): boolean {
  // Скрываем заголовок «Другое» (неявная группа): он не несёт информации.
  // Также скрываем заголовок, если всего одна группа — он избыточен.
  if (group === otherGroupLabel.value) return false
  return Object.keys(groupedItems.value).length > 1
}

async function handleDelete(item: NormalizedItem) {
  if (item.kind === 'bookmark') {
    await store.removeBookmark(item.id)
  } else {
    openDeleteLink(item.raw as ServiceLink)
  }
}

// ── Sortable.js drag-and-drop ─────────────────────────────────────────────
// Каждый .links-grid становится отдельным контейнером Sortable. По умолчанию
// контейнеры независимы (group: undefined) — перетаскивание между категориями
// заблокировано, что согласовано с UX группировки.
type SortableEntry = { el: HTMLElement; instance: Sortable }
const sortableInstances = new Map<string, SortableEntry>()
const sortableKey = (group: string) => `${activeTab.value}::${group}`

function bindSortable(el: Element | null, group: string) {
  const key = sortableKey(group)
  const existing = sortableInstances.get(key)
  if (!el) {
    if (existing) {
      existing.instance.destroy()
      sortableInstances.delete(key)
    }
    return
  }
  const htmlEl = el as HTMLElement
  if (existing && existing.el === htmlEl) return
  if (existing) existing.instance.destroy()

  const instance = Sortable.create(htmlEl, {
    handle: '.drag-handle',
    animation: 150,
    ghostClass: 'sortable-ghost',
    chosenClass: 'sortable-chosen',
    dragClass: 'sortable-drag',
    disabled: !canDrag.value,
    // Sortable делает drop-touch fallback автоматически на тач-устройствах.
    onEnd(evt) {
      const oldIdx = evt.oldIndex
      const newIdx = evt.newIndex
      if (oldIdx == null || newIdx == null || oldIdx === newIdx) return

      // Sortable уже переставил DOM-элемент. Откатываем, чтобы реактивным
      // состоянием по-прежнему управлял Vue (иначе список и DOM рассинхронятся).
      const item = evt.item
      const parent = evt.from
      parent.removeChild(item)
      const refNode = parent.children[oldIdx] ?? null
      parent.insertBefore(item, refNode)

      if (activeTab.value === 'my') {
        void reorderBookmarksInGroup(group, oldIdx, newIdx)
      } else {
        void reorderLinksInGroup(group, oldIdx, newIdx)
      }
    },
  })
  sortableInstances.set(key, { el: htmlEl, instance })
}

watch(canDrag, (val) => {
  for (const { instance } of sortableInstances.values()) {
    instance.option('disabled', !val)
  }
})

onUnmounted(() => {
  for (const { instance } of sortableInstances.values()) instance.destroy()
  sortableInstances.clear()
})

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
  } catch {
    message.error(t('errors.generic'))
    await store.loadBookmarks()
  }
}

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

  store.links.splice(0, store.links.length, ...newFlat)
  const payload = newFlat.map((l, i) => ({ id: l.id, sort_order: i }))
  try {
    await store.reorderLinks(payload)
  } catch {
    message.error(t('errors.generic'))
    await store.loadLinks()
  }
}

// ── Shared helpers ─────────────────────────────────────────────────────────
function faviconFor(url: string): string | null {
  try {
    const u = new URL(url)
    if (!['http:', 'https:'].includes(u.protocol)) return null
    // Proxy через бэкенд: убирает утечку реферера, кэшируется в Redis на 7 дней,
    // имеет negative-cache на недоступные домены — иконки не моргают при offline-сервисах.
    return `${BASE_URL}/bookmarks/favicon?url=${encodeURIComponent(u.origin)}`
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

function onIconError(e: Event) {
  const img = e.target as HTMLImageElement
  img.style.display = 'none'
}
</script>

<style scoped>
.links-wrap {
  max-width: 1200px;
  margin: 0 auto;
}

.page-head {
  margin-bottom: 24px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
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

/* ── Corporate links ──────────────────────────────────────────────────────── */
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

.link-card-wrap {
  position: relative;
}
.link-card-wrap:hover .link-admin-actions {
  opacity: 1;
}
.link-admin-actions {
  position: absolute;
  top: 50%;
  right: 10px;
  transform: translateY(-50%);
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s;
  background: var(--color-surface);
  border-radius: var(--radius-md);
  padding: 4px;
  box-shadow: var(--shadow-sm);
  z-index: 2;
}

.link-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  cursor: pointer;
  position: relative;
  text-align: left;
  font-family: inherit;
  width: 100%;
  transition: transform var(--t-base), box-shadow var(--t-base), border-color var(--t-base);
}
.link-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: var(--color-brand-sky);
}
.link-card:hover .link-arrow {
  color: var(--color-brand-red);
  transform: translate(2px, -2px);
}

.link-icon {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  overflow: hidden;
  color: var(--color-brand-navy);
}
[data-theme='dark'] .link-icon {
  background: rgba(255, 255, 255, 0.07) !important;
  color: rgba(255, 255, 255, 0.7);
}
.link-icon img {
  width: 26px;
  height: 26px;
  object-fit: contain;
}
.link-info {
  flex: 1;
  min-width: 0;
}
.link-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text);
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.link-desc {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.link-url {
  font-size: 11px;
  color: var(--color-text-subtle);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.link-arrow {
  flex-shrink: 0;
  color: var(--color-text-subtle);
  transition: transform var(--t-base), color var(--t-base);
}

.sso-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  background: rgba(74, 144, 196, 0.12);
  color: var(--color-brand-sky);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

/* ── Modal forms ──────────────────────────────────────────────────────────── */
.modal-form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
}
.modal-form-checks {
  display: flex;
  gap: 24px;
  margin-top: 4px;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.icon-upload-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.icon-preview-wrap {
  position: relative;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
}
.icon-preview {
  width: 40px;
  height: 40px;
  object-fit: contain;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
}
.icon-preview-remove {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 18px !important;
  height: 18px !important;
  min-width: 18px !important;
  font-size: 12px;
}

/* ── Drag-to-reorder (Sortable.js) ────────────────────────────────────── */
.link-card { text-decoration: none; color: inherit; }
.link-card-wrap--draggable .drag-handle { cursor: grab; }
.link-card-wrap--draggable .drag-handle:active { cursor: grabbing; }

/* Placeholder в позиции переносимого элемента */
.sortable-ghost > .link-card {
  opacity: 0.35;
  border-color: var(--color-brand-sky);
  border-style: dashed;
  background: transparent;
}
.sortable-ghost > .link-card > * { visibility: hidden; }

/* Сам перетаскиваемый клон, висящий под курсором */
.sortable-drag > .link-card {
  box-shadow: var(--shadow-md);
  transform: rotate(0.6deg);
  cursor: grabbing;
}

.drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  flex-shrink: 0;
  margin-right: -4px;
  margin-left: -4px;
  color: var(--color-text-subtle);
  opacity: 0;
  transition: opacity var(--t-base);
  cursor: grab;
}
.link-card-wrap--draggable:hover .drag-handle,
.link-card-wrap--draggable:focus-within .drag-handle {
  opacity: 0.7;
}
.drag-handle:hover { opacity: 1 !important; }

@media (max-width: 640px) {
  .page-head { flex-direction: column; align-items: stretch; }
  /* На тач-устройствах ручка всегда видна — Sortable работает по long-press. */
  .link-card-wrap--draggable .drag-handle { opacity: 0.7; }
}
</style>
