<template>
  <AppLayout>
    <template #header-title><span>{{ t('nav.admin') }}</span></template>

    <div class="admin-wrap">
      <header class="page-head">
        <h1 class="page-head__title">{{ t('admin.title') }}</h1>
      </header>

      <n-tabs v-model:value="activeTab" type="line" animated>
        <!-- ── USERS ── -->
        <n-tab-pane name="users" :tab="t('admin.tabs.users')">
          <div class="tab-toolbar">
            <n-input
              v-model:value="userSearch"
              :placeholder="t('common.search')"
              clearable
              style="max-width:260px"
            >
              <template #prefix><n-icon><SearchOutline /></n-icon></template>
            </n-input>
            <n-button :loading="syncing" @click="syncUsers">
              <template #icon><n-icon><SyncOutline /></n-icon></template>
              {{ syncing ? t('admin.users.syncing') : t('admin.users.syncFromKeycloak') }}
            </n-button>
          </div>

          <n-data-table
            :columns="userColumns"
            :data="filteredUsers"
            :loading="loadingUsers"
            :pagination="{ pageSize: 20 }"
            :row-key="(row: UserPublic) => row.id"
            striped
            class="data-table"
          />
        </n-tab-pane>

        <!-- ── SERVICE LINKS ── -->
        <n-tab-pane name="links" :tab="t('admin.tabs.links')">
          <div class="tab-toolbar">
            <n-input
              v-model:value="linkSearch"
              :placeholder="t('common.search')"
              clearable
              style="max-width:260px"
            >
              <template #prefix><n-icon><SearchOutline /></n-icon></template>
            </n-input>
            <n-button type="primary" @click="openAddLink">
              <template #icon><n-icon><AddOutline /></n-icon></template>
              {{ t('admin.links.add') }}
            </n-button>
          </div>

          <n-data-table
            :columns="linkColumns"
            :data="filteredLinks"
            :loading="loadingLinks"
            :pagination="{ pageSize: 20 }"
            :row-key="(row: ServiceLink) => row.id"
            striped
            class="data-table"
          />
        </n-tab-pane>

        <!-- ── BRANDING ── -->
        <n-tab-pane name="branding" :tab="t('admin.branding.tab')">
          <div class="branding-wrap">

            <!-- Logo -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.branding.logoTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.branding.logoHint') }}</div>
              <div class="branding-logo-row">
                <div class="branding-logo-preview">
                  <img v-if="currentLogoUrl" :src="currentLogoUrl" class="branding-logo-img" alt="Logo" />
                  <div v-else class="branding-logo-placeholder">
                    <div class="logo-mark-preview"><span class="logo-mark-preview__dot" /></div>
                    <span class="branding-logo-placeholder__text">{{ t('admin.branding.logoDefault') }}</span>
                  </div>
                </div>
                <div class="branding-logo-actions">
                  <input ref="logoInputRef" type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" style="display:none" @change="onLogoFileChange" />
                  <n-button type="primary" :loading="logoUploading" @click="logoInputRef?.click()">{{ t('admin.branding.uploadLogo') }}</n-button>
                  <n-button v-if="currentLogoUrl" :loading="logoResetting" @click="onLogoReset">{{ t('admin.branding.resetLogo') }}</n-button>
                </div>
              </div>
            </div>

            <!-- Favicon -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.branding.faviconTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.branding.faviconHint') }}</div>
              <div class="branding-logo-actions" style="flex-direction:row;align-items:center;gap:12px">
                <img v-if="currentFaviconUrl" :src="currentFaviconUrl" class="branding-favicon-preview" alt="Favicon" />
                <input ref="faviconInputRef" type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp,image/x-icon" style="display:none" @change="onFaviconFileChange" />
                <n-button type="primary" size="small" :loading="faviconUploading" @click="faviconInputRef?.click()">{{ t('admin.branding.uploadFavicon') }}</n-button>
                <n-button v-if="currentFaviconUrl" size="small" :loading="faviconResetting" @click="onFaviconReset">{{ t('admin.branding.resetFavicon') }}</n-button>
              </div>
            </div>

            <!-- Login background -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.branding.loginBgTitle') }}</div>
              <div class="branding-section__hint">{{ t('admin.branding.loginBgHint') }}</div>
              <div class="branding-logo-row">
                <div v-if="currentLoginBgUrl" class="branding-loginbg-preview">
                  <img :src="currentLoginBgUrl" alt="Login BG" class="branding-loginbg-img" />
                </div>
                <div class="branding-logo-actions">
                  <input ref="loginBgInputRef" type="file" accept="image/png,image/jpeg,image/webp" style="display:none" @change="onLoginBgFileChange" />
                  <n-button type="primary" size="small" :loading="loginBgUploading" @click="loginBgInputRef?.click()">{{ t('admin.branding.uploadLoginBg') }}</n-button>
                  <n-button v-if="currentLoginBgUrl" size="small" :loading="loginBgResetting" @click="onLoginBgReset">{{ t('admin.branding.resetLoginBg') }}</n-button>
                </div>
              </div>
            </div>

            <!-- General settings -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.branding.generalTitle') }}</div>
              <div class="branding-fields">
                <n-form-item :label="t('admin.branding.portalName')" style="margin-bottom:0">
                  <n-input v-model:value="brandingForm.portal_name" :placeholder="t('admin.branding.portalNamePlaceholder')" />
                </n-form-item>
                <n-form-item :label="t('admin.branding.portalTagline')" style="margin-bottom:0">
                  <n-input v-model:value="brandingForm.portal_tagline" :placeholder="t('admin.branding.portalTaglinePlaceholder')" />
                </n-form-item>
                <n-form-item :label="t('admin.branding.accentColor')" style="margin-bottom:0">
                  <div class="branding-color-row">
                    <input type="color" v-model="brandingForm.accent_color" class="branding-color-input" />
                    <n-input v-model:value="brandingForm.accent_color" style="width:120px;font-family:monospace" />
                    <div class="branding-color-swatch" :style="`background:${brandingForm.accent_color}`" />
                  </div>
                </n-form-item>
                <n-form-item :label="t('admin.branding.welcomeSubtitle')" style="margin-bottom:0">
                  <n-input v-model:value="brandingForm.welcome_subtitle" type="textarea" :rows="2" :placeholder="t('admin.branding.welcomeSubtitlePlaceholder')" />
                </n-form-item>
              </div>
              <n-button type="primary" :loading="brandingFormSaving" style="margin-top:16px" @click="saveBrandingForm">
                {{ t('common.save') }}
              </n-button>
            </div>

            <!-- Banner -->
            <div class="branding-section">
              <div class="branding-section__title">{{ t('admin.branding.bannerTitle') }}</div>
              <div class="branding-fields">
                <n-form-item :label="t('admin.branding.bannerEnabled')" style="margin-bottom:0">
                  <n-switch v-model:value="brandingForm.banner_enabled" />
                </n-form-item>
                <n-form-item :label="t('admin.branding.bannerText')" style="margin-bottom:0">
                  <n-input v-model:value="brandingForm.banner_text" type="textarea" :rows="2" :placeholder="t('admin.branding.bannerTextPlaceholder')" />
                </n-form-item>
                <n-form-item :label="t('admin.branding.bannerType')" style="margin-bottom:0">
                  <n-select
                    v-model:value="brandingForm.banner_type"
                    :options="bannerTypeOptions"
                    style="width:200px"
                  />
                </n-form-item>
                <n-form-item :label="t('admin.branding.bannerExpires')" style="margin-bottom:0">
                  <n-input
                    v-model:value="brandingForm.banner_expires_at"
                    :placeholder="t('admin.branding.bannerExpiresPlaceholder')"
                    clearable
                    style="width:220px"
                  />
                  <span style="margin-left:8px;font-size:12px;color:var(--color-text-muted)">{{ t('admin.branding.bannerExpiresHint') }}</span>
                </n-form-item>
              </div>
              <n-button type="primary" :loading="brandingFormSaving" style="margin-top:16px" @click="saveBrandingForm">
                {{ t('common.save') }}
              </n-button>
            </div>

          </div>
        </n-tab-pane>
      </n-tabs>
    </div>

    <!-- ── LINK FORM MODAL ── -->
    <n-modal
      v-model:show="linkModalOpen"
      :title="editingLink ? t('admin.links.editTitle') : t('admin.links.addTitle')"
      preset="card"
      style="width:540px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form :model="linkForm" :rules="linkRules" ref="linkFormRef" label-placement="top">
        <div class="form-row">
          <n-form-item :label="t('admin.links.form.titleLabel')" path="title">
            <n-input v-model:value="linkForm.title" :placeholder="t('admin.links.form.titlePlaceholder')" />
          </n-form-item>
          <n-form-item :label="t('admin.links.form.urlLabel')" path="url">
            <n-input v-model:value="linkForm.url" :placeholder="t('admin.links.form.urlPlaceholder')" />
          </n-form-item>
        </div>
        <div class="form-row">
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
              <n-button
                size="tiny" circle quaternary type="error"
                class="icon-preview-remove"
                @click="removeIcon"
              >×</n-button>
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
        <div class="form-checks">
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
import { ref, computed, onMounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NTabs, NTabPane, NDataTable, NButton, NInput, NInputNumber, NIcon,
  NModal, NForm, NFormItem, NCheckbox, NTag, NSelect, NUpload, NSwitch,
  useMessage, type DataTableColumns, type UploadFileInfo,
} from 'naive-ui'
import { SearchOutline, SyncOutline, AddOutline, CreateOutline, TrashOutline, ShieldCheckmarkOutline } from '@vicons/ionicons5'
import AppLayout from '../components/AppLayout.vue'
import { fetchUsers, changeUserRole, syncUsersFromKeycloak, type UserPublic } from '../api/users'
import { fetchLinks, createLink, updateLink, deleteLink, uploadLinkIcon, deleteLinkIcon, type ServiceLink, type CreateLinkDto } from '../api/links'
import { isSafeHttpUrl } from '../utils/url'
import { useBrandingStore, type BrandingSettings } from '../stores/branding'

const { t } = useI18n()
const message = useMessage()

const activeTab = ref('users')

// ── Users ──────────────────────────────────────────────────────────────────
const users = ref<UserPublic[]>([])
const loadingUsers = ref(false)
const syncing = ref(false)
const userSearch = ref('')

const filteredUsers = computed(() => {
  const q = userSearch.value.trim().toLowerCase()
  if (!q) return users.value
  return users.value.filter(u =>
    u.full_name.toLowerCase().includes(q) ||
    u.email.toLowerCase().includes(q) ||
    (u.department ?? '').toLowerCase().includes(q),
  )
})

const roleOptions = computed(() => [
  { label: t('admin.users.role.reader'), value: 'reader' },
  { label: t('admin.users.role.editor'), value: 'editor' },
  { label: t('admin.users.role.admin'), value: 'admin' },
])

const userColumns = computed<DataTableColumns<UserPublic>>(() => [
  {
    title: t('admin.users.columns.fullName'),
    key: 'full_name',
    sorter: 'default',
    ellipsis: { tooltip: true },
  },
  {
    title: t('admin.users.columns.email'),
    key: 'email',
    ellipsis: { tooltip: true },
  },
  {
    title: t('admin.users.columns.department'),
    key: 'department',
    ellipsis: { tooltip: true },
    render: (row) => row.department ?? '—',
  },
  {
    title: t('admin.users.columns.role'),
    key: 'role',
    width: 160,
    render: (row) =>
      h(NSelect, {
        value: row.role,
        options: roleOptions.value,
        size: 'small',
        style: 'width:140px',
        onUpdateValue: (val: string) => handleRoleChange(row, val),
      }),
  },
  {
    title: t('admin.users.columns.authSource'),
    key: 'auth_source',
    width: 120,
    render: (row) =>
      h(NTag, { size: 'small', type: (row as any).auth_source === 'local' ? 'warning' : 'info', bordered: false },
        { default: () => (row as any).auth_source === 'local' ? 'Local' : 'SSO' }),
  },
])

async function loadUsers() {
  loadingUsers.value = true
  try {
    const res = await fetchUsers({ page_size: 300 })
    users.value = res.items
  } catch {
    message.error(t('errors.generic'))
  } finally {
    loadingUsers.value = false
  }
}

async function handleRoleChange(user: UserPublic, role: string) {
  try {
    const updated = await changeUserRole(user.id, role)
    const idx = users.value.findIndex(u => u.id === user.id)
    if (idx !== -1) users.value[idx] = { ...users.value[idx], role: updated.role }
    message.success(t('admin.users.roleChanged'))
  } catch {
    message.error(t('errors.generic'))
  }
}

async function syncUsers() {
  syncing.value = true
  try {
    await syncUsersFromKeycloak()
    message.success(t('admin.users.syncOk'))
    await loadUsers()
  } catch {
    message.error(t('errors.generic'))
  } finally {
    syncing.value = false
  }
}

// ── Links ──────────────────────────────────────────────────────────────────
const links = ref<ServiceLink[]>([])
const loadingLinks = ref(false)
const linkSearch = ref('')

const filteredLinks = computed(() => {
  const q = linkSearch.value.trim().toLowerCase()
  if (!q) return links.value
  return links.value.filter(l =>
    l.title.toLowerCase().includes(q) ||
    l.url.toLowerCase().includes(q) ||
    (l.category ?? '').toLowerCase().includes(q),
  )
})

const linkModalOpen = ref(false)
const savingLink = ref(false)
const editingLink = ref<ServiceLink | null>(null)
const linkFormRef = ref()

const iconFile = ref<File | null>(null)
const iconPreview = ref<string | null>(null)
const iconRemoved = ref(false)

function onIconFileChange({ file }: { file: UploadFileInfo }) {
  if (file.file) {
    iconFile.value = file.file
    iconPreview.value = URL.createObjectURL(file.file)
    iconRemoved.value = false
  }
}

function removeIcon() {
  iconFile.value = null
  iconPreview.value = null
  iconRemoved.value = true
}

function resetIconState() {
  iconFile.value = null
  iconPreview.value = null
  iconRemoved.value = false
}

const emptyLinkForm = (): CreateLinkDto & { id?: string } => ({
  title: '',
  url: '',
  description: null,
  category: null,
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

const deleteConfirmOpen = ref(false)
const deletingLink = ref<ServiceLink | null>(null)

const linkColumns = computed<DataTableColumns<ServiceLink>>(() => [
  {
    title: '',
    key: 'icon',
    width: 44,
    align: 'center',
    render: (row) =>
      row.icon_url
        ? h('img', { src: row.icon_url, style: 'width:24px;height:24px;object-fit:contain;vertical-align:middle', alt: '' })
        : null,
  },
  {
    title: t('admin.links.columns.title'),
    key: 'title',
    sorter: 'default',
    ellipsis: { tooltip: true },
  },
  {
    title: t('admin.links.columns.url'),
    key: 'url',
    ellipsis: { tooltip: true },
    render: (row) => h('span', { style: 'font-size:12px;color:var(--color-text-muted)' }, row.url),
  },
  {
    title: t('admin.links.columns.category'),
    key: 'category',
    width: 130,
    render: (row) => row.category ?? '—',
  },
  {
    title: t('admin.links.columns.sso'),
    key: 'supports_sso',
    width: 70,
    align: 'center',
    render: (row) =>
      row.supports_sso
        ? h(NIcon, { color: 'var(--color-brand-sky)', size: 18 }, { default: () => h(ShieldCheckmarkOutline) })
        : h('span', { style: 'color:var(--color-text-subtle)' }, '—'),
  },
  {
    title: t('admin.links.columns.active'),
    key: 'is_active',
    width: 90,
    align: 'center',
    render: (row) =>
      h(NTag, { size: 'small', type: row.is_active ? 'success' : 'default', bordered: false },
        { default: () => row.is_active ? t('common.yes') : t('common.no') }),
  },
  {
    title: t('admin.links.columns.actions'),
    key: 'actions',
    width: 100,
    align: 'center',
    render: (row) =>
      h('div', { style: 'display:flex;gap:6px;justify-content:center' }, [
        h(NButton, {
          size: 'small', quaternary: true, circle: true,
          title: t('common.edit'),
          onClick: () => openEditLink(row),
        }, { icon: () => h(NIcon, null, { default: () => h(CreateOutline) }) }),
        h(NButton, {
          size: 'small', quaternary: true, circle: true, type: 'error',
          title: t('common.delete'),
          onClick: () => openDeleteLink(row),
        }, { icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) }),
      ]),
  },
])

async function loadLinks() {
  loadingLinks.value = true
  try {
    const res = await fetchLinks({ include_inactive: true })
    links.value = res.items
  } catch {
    message.error(t('errors.generic'))
  } finally {
    loadingLinks.value = false
  }
}

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
  try {
    await linkFormRef.value?.validate()
  } catch {
    return
  }
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
      const idx = links.value.findIndex(l => l.id === editingLink.value!.id)
      if (idx !== -1) links.value[idx] = saved
    } else {
      saved = await createLink(dto)
      links.value.unshift(saved)
    }

    if (iconFile.value) {
      const withIcon = await uploadLinkIcon(saved.id, iconFile.value)
      const idx = links.value.findIndex(l => l.id === saved.id)
      if (idx !== -1) links.value[idx] = withIcon
    } else if (iconRemoved.value && editingLink.value?.icon_url) {
      await deleteLinkIcon(saved.id)
      const idx = links.value.findIndex(l => l.id === saved.id)
      if (idx !== -1) links.value[idx] = { ...links.value[idx], icon_url: null }
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
    links.value = links.value.filter(l => l.id !== deletingLink.value!.id)
    message.success(t('admin.links.deleted'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    deletingLink.value = null
  }
}

// ── Branding ────────────────────────────────────────────────────────────────
const currentLogoUrl = ref<string | null>(null)
const logoInputRef = ref<HTMLInputElement | null>(null)
const logoUploading = ref(false)
const logoResetting = ref(false)

async function loadCurrentLogo() {
  try {
    const res = await fetch('/api/v1/branding/logo', { credentials: 'include' })
    if (res.ok) currentLogoUrl.value = `/api/v1/branding/logo?t=${Date.now()}`
    else currentLogoUrl.value = null
  } catch {
    currentLogoUrl.value = null
  }
}

async function onLogoFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''

  if (file.size > 2 * 1024 * 1024) {
    message.error(t('admin.branding.logoTooBig'))
    return
  }

  logoUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch('/api/v1/admin/branding/logo', {
      method: 'POST',
      credentials: 'include',
      body: fd,
    })
    if (!res.ok) throw new Error()
    currentLogoUrl.value = `/api/v1/branding/logo?t=${Date.now()}`
    window.dispatchEvent(new CustomEvent('logo-updated'))
    message.success(t('admin.branding.logoUploaded'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    logoUploading.value = false
  }
}

async function onLogoReset() {
  logoResetting.value = true
  try {
    const res = await fetch('/api/v1/admin/branding/logo', { method: 'DELETE', credentials: 'include' })
    if (!res.ok) throw new Error()
    currentLogoUrl.value = null
    window.dispatchEvent(new CustomEvent('logo-updated'))
    message.success(t('admin.branding.logoReset'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    logoResetting.value = false
  }
}

// ── Favicon ──────────────────────────────────────────────────────────────────
const currentFaviconUrl = ref<string | null>(null)
const faviconInputRef = ref<HTMLInputElement | null>(null)
const faviconUploading = ref(false)
const faviconResetting = ref(false)

async function loadCurrentFavicon() {
  try {
    const r = await fetch('/api/v1/branding/favicon', { method: 'HEAD', credentials: 'include' })
    currentFaviconUrl.value = r.ok ? `/api/v1/branding/favicon?t=${Date.now()}` : null
  } catch { currentFaviconUrl.value = null }
}

async function onFaviconFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  if (file.size > 2 * 1024 * 1024) { message.error(t('admin.branding.logoTooBig')); return }
  faviconUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch('/api/v1/admin/branding/favicon', { method: 'POST', credentials: 'include', body: fd })
    if (!res.ok) throw new Error()
    currentFaviconUrl.value = `/api/v1/branding/favicon?t=${Date.now()}`
    brandingStore.load()
    message.success(t('admin.branding.faviconUploaded'))
  } catch { message.error(t('errors.generic')) }
  finally { faviconUploading.value = false }
}

async function onFaviconReset() {
  faviconResetting.value = true
  try {
    const res = await fetch('/api/v1/admin/branding/favicon', { method: 'DELETE', credentials: 'include' })
    if (!res.ok) throw new Error()
    currentFaviconUrl.value = null
    message.success(t('admin.branding.faviconReset'))
  } catch { message.error(t('errors.generic')) }
  finally { faviconResetting.value = false }
}

// ── Login background ──────────────────────────────────────────────────────────
const currentLoginBgUrl = ref<string | null>(null)
const loginBgInputRef = ref<HTMLInputElement | null>(null)
const loginBgUploading = ref(false)
const loginBgResetting = ref(false)

async function loadCurrentLoginBg() {
  try {
    const r = await fetch('/api/v1/branding/login-bg', { method: 'HEAD', credentials: 'include' })
    currentLoginBgUrl.value = r.ok ? `/api/v1/branding/login-bg?t=${Date.now()}` : null
  } catch { currentLoginBgUrl.value = null }
}

async function onLoginBgFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = ''
  if (file.size > 2 * 1024 * 1024) { message.error(t('admin.branding.logoTooBig')); return }
  loginBgUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch('/api/v1/admin/branding/login-bg', { method: 'POST', credentials: 'include', body: fd })
    if (!res.ok) throw new Error()
    currentLoginBgUrl.value = `/api/v1/branding/login-bg?t=${Date.now()}`
    message.success(t('admin.branding.loginBgUploaded'))
  } catch { message.error(t('errors.generic')) }
  finally { loginBgUploading.value = false }
}

async function onLoginBgReset() {
  loginBgResetting.value = true
  try {
    const res = await fetch('/api/v1/admin/branding/login-bg', { method: 'DELETE', credentials: 'include' })
    if (!res.ok) throw new Error()
    currentLoginBgUrl.value = null
    message.success(t('admin.branding.loginBgReset'))
  } catch { message.error(t('errors.generic')) }
  finally { loginBgResetting.value = false }
}

// ── Branding form (settings) ──────────────────────────────────────────────────
const brandingStore = useBrandingStore()
const brandingFormSaving = ref(false)
const brandingForm = ref<BrandingSettings>({ ...brandingStore.settings })

const bannerTypeOptions = computed(() => [
  { label: t('admin.branding.bannerTypeInfo'), value: 'info' },
  { label: t('admin.branding.bannerTypeWarning'), value: 'warning' },
  { label: t('admin.branding.bannerTypeError'), value: 'error' },
  { label: t('admin.branding.bannerTypeSuccess'), value: 'success' },
])

async function loadBrandingForm() {
  await brandingStore.load()
  brandingForm.value = { ...brandingStore.settings }
}

async function saveBrandingForm() {
  brandingFormSaving.value = true
  try {
    await brandingStore.save(brandingForm.value)
    message.success(t('admin.branding.settingsSaved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    brandingFormSaving.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadUsers(), loadLinks(), loadCurrentLogo(), loadCurrentFavicon(), loadCurrentLoginBg(), loadBrandingForm()])
})
</script>

<style scoped>
.admin-wrap {
  max-width: 1280px;
  margin: 0 auto;
}
.page-head {
  margin-bottom: 20px;
}
.page-head__title {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-text);
}

.tab-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.data-table {
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--color-border);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
}

.form-checks {
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

.branding-wrap {
  max-width: 640px;
  padding-top: 8px;
}

.branding-section {
  padding: 24px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
}

.branding-section__title {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 4px;
}

.branding-section__hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 20px;
}

.branding-logo-row {
  display: flex;
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
}

.branding-logo-preview {
  width: 180px;
  height: 64px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  flex-shrink: 0;
}

.branding-logo-img {
  max-width: 160px;
  max-height: 52px;
  object-fit: contain;
}

.branding-logo-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.branding-logo-placeholder__text {
  font-size: 11px;
  color: var(--color-text-secondary);
}

.logo-mark-preview {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-md);
  background: var(--gradient-hero);
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo-mark-preview__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #fff;
}

.branding-logo-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.branding-favicon-preview {
  width: 32px;
  height: 32px;
  object-fit: contain;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  flex-shrink: 0;
}

.branding-loginbg-preview {
  width: 240px;
  height: 120px;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  flex-shrink: 0;
}

.branding-loginbg-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.branding-fields {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.branding-color-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.branding-color-input {
  width: 48px;
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 2px;
  cursor: pointer;
  background: none;
}

.branding-color-swatch {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border);
  flex-shrink: 0;
}

.branding-section + .branding-section {
  margin-top: 16px;
}
</style>
