<template>
  <AppLayout>
    <template #header-title><span>{{ t('nav.links') }}</span></template>

    <div class="links-wrap">
      <header class="page-head">
        <div>
          <h1 class="page-head__title">{{ t('nav.links') }}</h1>
          <p class="page-head__sub">{{ t('links.pageSub') }}</p>
        </div>
        <n-button v-if="auth.isAdmin" type="primary" @click="openAddLink">
          <template #icon><n-icon><AddOutline /></n-icon></template>
          {{ t('admin.links.add') }}
        </n-button>
      </header>

      <n-spin v-if="store.loadingLinks" style="margin:60px auto;display:block" />
      <template v-else>
        <EmptyState
          v-if="!Object.keys(store.groupedLinks).length"
          variant="default"
          :title="t('links.empty')"
          :description="t('links.emptyHint')"
        />

        <template v-for="(group, category) in store.groupedLinks" :key="category">
          <section class="category-section">
            <h3 class="category-title">{{ category }}</h3>
            <div class="links-grid">
              <div v-for="link in group" :key="link.id" class="link-card-wrap">
                <button
                  type="button"
                  class="link-card"
                  @click="store.openLink(link)"
                >
                  <div class="link-icon" :style="{ background: colorFor(link.url) }">
                    <img
                      v-if="link.icon_url"
                      :src="link.icon_url"
                      :alt="link.title"
                      @error="onIconError($event)"
                    />
                    <img
                      v-else-if="faviconFor(link.url)"
                      :src="faviconFor(link.url)!"
                      :alt="link.title"
                      @error="onIconError($event)"
                    />
                    <n-icon v-else size="22"><LinkOutline /></n-icon>
                  </div>
                  <div class="link-info">
                    <div class="link-title">
                      {{ link.title }}
                      <span v-if="link.supports_sso" class="sso-badge" :title="t('links.sso')">
                        <n-icon size="12"><ShieldCheckmarkOutline /></n-icon>
                        SSO
                      </span>
                    </div>
                    <div v-if="link.description" class="link-desc">{{ link.description }}</div>
                    <div class="link-url">{{ shortUrl(link.url) }}</div>
                  </div>
                  <n-icon class="link-arrow" size="16"><OpenOutline /></n-icon>
                </button>
                <div v-if="auth.isAdmin" class="link-admin-actions">
                  <n-button size="tiny" quaternary circle :title="t('common.edit')" @click.stop="openEditLink(link)">
                    <template #icon><n-icon size="13"><CreateOutline /></n-icon></template>
                  </n-button>
                  <n-button size="tiny" quaternary circle type="error" :title="t('common.delete')" @click.stop="openDeleteLink(link)">
                    <template #icon><n-icon size="13"><TrashOutline /></n-icon></template>
                  </n-button>
                </div>
              </div>
            </div>
          </section>
        </template>
      </template>
    </div>
    <!-- ── LINK FORM MODAL ── -->
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
        <n-form-item :label="t('admin.links.form.iconUrlLabel')">
          <n-input v-model:value="linkForm.icon_url" :placeholder="t('admin.links.form.iconUrlPlaceholder')" clearable />
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

    <!-- ── DELETE CONFIRM ── -->
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
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NSpin, NIcon, NButton, NModal, NForm, NFormItem,
  NInput, NInputNumber, NCheckbox, useMessage,
} from 'naive-ui'
import { LinkOutline, ShieldCheckmarkOutline, OpenOutline, AddOutline, CreateOutline, TrashOutline } from '@vicons/ionicons5'
import AppLayout from '../components/AppLayout.vue'
import EmptyState from '../components/EmptyState.vue'
import { useLinksStore } from '../stores/links'
import { useAuthStore } from '../stores/auth'
import { createLink, updateLink, deleteLink, type ServiceLink, type CreateLinkDto } from '../api/links'
import { isSafeHttpUrl } from '../utils/url'

const { t } = useI18n()
const store = useLinksStore()
const auth = useAuthStore()
const message = useMessage()

onMounted(() => store.loadLinks())

// ── Admin link management ───────────────────────────────────────────────────
const linkModalOpen = ref(false)
const savingLink = ref(false)
const editingLink = ref<ServiceLink | null>(null)
const linkFormRef = ref()
const deleteConfirmOpen = ref(false)
const deletingLink = ref<ServiceLink | null>(null)

const emptyLinkForm = () => ({
  title: '',
  url: '',
  icon_url: null as string | null,
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
  linkModalOpen.value = true
}

function openEditLink(link: ServiceLink) {
  editingLink.value = link
  linkForm.value = {
    title: link.title,
    url: link.url,
    icon_url: link.icon_url,
    description: link.description,
    category: link.category,
    sort_order: link.sort_order,
    supports_sso: link.supports_sso,
    is_active: link.is_active,
  }
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
      icon_url: linkForm.value.icon_url || null,
      description: linkForm.value.description || null,
      category: linkForm.value.category || null,
      sort_order: linkForm.value.sort_order ?? 0,
      supports_sso: linkForm.value.supports_sso,
      is_active: linkForm.value.is_active,
    }
    if (editingLink.value) {
      const updated = await updateLink(editingLink.value.id, dto)
      const idx = store.links.findIndex(l => l.id === editingLink.value!.id)
      if (idx !== -1) store.links.splice(idx, 1, updated)
    } else {
      const created = await createLink(dto)
      store.links.splice(0, 0, created)
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
  top: 6px;
  right: 6px;
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s;
  background: var(--color-surface);
  border-radius: var(--radius-md);
  padding: 2px;
  box-shadow: var(--shadow-sm);
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
</style>
