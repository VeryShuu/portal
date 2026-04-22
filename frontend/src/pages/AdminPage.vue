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
  NModal, NForm, NFormItem, NCheckbox, NTag, NSelect, NUpload,
  useMessage, type DataTableColumns, type UploadFileInfo,
} from 'naive-ui'
import { SearchOutline, SyncOutline, AddOutline, CreateOutline, TrashOutline, ShieldCheckmarkOutline } from '@vicons/ionicons5'
import AppLayout from '../components/AppLayout.vue'
import { fetchUsers, changeUserRole, syncUsersFromKeycloak, type UserPublic } from '../api/users'
import { fetchLinks, createLink, updateLink, deleteLink, uploadLinkIcon, deleteLinkIcon, type ServiceLink, type CreateLinkDto } from '../api/links'
import { isSafeHttpUrl } from '../utils/url'

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

onMounted(async () => {
  await Promise.all([loadUsers(), loadLinks()])
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
</style>
