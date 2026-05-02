<template>
  <div>
    <div class="tab-toolbar">
      <n-input
        v-model:value="userSearch"
        :placeholder="t('common.search')"
        clearable
        style="max-width:260px"
      >
        <template #prefix><n-icon><SearchOutline /></n-icon></template>
      </n-input>
      <n-button type="primary" @click="openCreateModal">
        <template #icon><n-icon><AddOutline /></n-icon></template>
        {{ t('admin.users.addLocal') }}
      </n-button>
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

    <n-modal
      v-model:show="createModalOpen"
      :title="t('admin.users.createModal.title')"
      preset="card"
      style="width:480px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form :model="createForm" :rules="createRules" ref="createFormRef" label-placement="top">
        <n-form-item :label="t('admin.users.form.email')" path="email">
          <n-input v-model:value="createForm.email" :placeholder="t('admin.users.form.emailPlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('admin.users.form.fullName')" path="full_name">
          <n-input v-model:value="createForm.full_name" :placeholder="t('admin.users.form.fullNamePlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('admin.users.form.password')" path="password">
          <n-input
            v-model:value="createForm.password"
            type="password"
            show-password-on="click"
            :placeholder="t('admin.users.form.passwordPlaceholder')"
          />
        </n-form-item>
        <n-form-item :label="t('admin.users.columns.role')" path="role">
          <n-select v-model:value="createForm.role" :options="roleOptions" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="createModalOpen = false">{{ t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="savingCreate" @click="submitCreate">{{ t('common.save') }}</n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      v-model:show="editModalOpen"
      :title="t('admin.users.editModal.title')"
      preset="card"
      style="width:480px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form :model="editForm" :rules="editRules" ref="editFormRef" label-placement="top">
        <n-form-item :label="t('admin.users.form.fullName')" path="full_name">
          <n-input v-model:value="editForm.full_name" :placeholder="t('admin.users.form.fullNamePlaceholder')" />
        </n-form-item>
        <n-form-item :label="t('admin.users.form.department')">
          <n-input v-model:value="editForm.department" :placeholder="t('admin.users.form.departmentPlaceholder')" clearable />
        </n-form-item>
        <n-form-item :label="t('admin.users.form.position')">
          <n-input v-model:value="editForm.position" :placeholder="t('admin.users.form.positionPlaceholder')" clearable />
        </n-form-item>
        <n-form-item :label="t('admin.users.form.phone')">
          <n-input v-model:value="editForm.phone" :placeholder="t('admin.users.form.phonePlaceholder')" clearable />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="editModalOpen = false">{{ t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="savingEdit" @click="submitEdit">{{ t('common.save') }}</n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      v-model:show="resetPwdModalOpen"
      :title="t('admin.users.resetPwdModal.title')"
      preset="card"
      style="width:400px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form :model="resetPwdForm" :rules="resetPwdRules" ref="resetPwdFormRef" label-placement="top">
        <n-form-item :label="t('admin.users.form.newPassword')" path="password">
          <n-input
            v-model:value="resetPwdForm.password"
            type="password"
            show-password-on="click"
            :placeholder="t('admin.users.form.passwordPlaceholder')"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="resetPwdModalOpen = false">{{ t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="savingResetPwd" @click="submitResetPwd">{{ t('common.save') }}</n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      v-model:show="deleteConfirmOpen"
      :title="t('admin.users.deleteModal.title', { name: deletingUser?.full_name ?? '' })"
      preset="dialog"
      type="warning"
      :positive-text="t('common.delete')"
      :negative-text="t('common.cancel')"
      @positive-click="confirmDelete"
    >
      {{ t('admin.users.deleteModal.hint') }}
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  NDataTable, NButton, NInput, NIcon, NTag, NSelect, NModal, NForm, NFormItem,
  useMessage, type DataTableColumns,
} from 'naive-ui'
import {
  SearchOutline, SyncOutline, AddOutline, CreateOutline, TrashOutline, KeyOutline, EyeOutline,
} from '@vicons/ionicons5'
import {
  fetchUsers, changeUserRole, syncUsersFromKeycloak,
  adminCreateLocalUser, adminPatchUserProfile, adminResetUserPassword, adminDeleteUser,
  type UserPublic,
} from '../../../api/users'

const { t } = useI18n()
const message = useMessage()
const router = useRouter()

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

const createModalOpen = ref(false)
const savingCreate = ref(false)
const createFormRef = ref()
const createForm = ref({ email: '', full_name: '', password: '', role: 'reader' as 'reader' | 'editor' | 'admin' })
const createRules = computed(() => ({
  email: [{ required: true, message: t('admin.users.form.required'), trigger: 'blur' }],
  full_name: [{ required: true, message: t('admin.users.form.required'), trigger: 'blur' }],
  password: [
    { required: true, message: t('admin.users.form.required'), trigger: 'blur' },
    { min: 8, message: t('admin.users.form.passwordMin'), trigger: 'blur' },
  ],
}))

const editModalOpen = ref(false)
const savingEdit = ref(false)
const editFormRef = ref()
const editingUser = ref<UserPublic | null>(null)
const editForm = ref({ full_name: '', department: '', position: '', phone: '' })
const editRules = computed(() => ({
  full_name: [{ required: true, message: t('admin.users.form.required'), trigger: 'blur' }],
}))

const resetPwdModalOpen = ref(false)
const savingResetPwd = ref(false)
const resetPwdFormRef = ref()
const resetPwdUser = ref<UserPublic | null>(null)
const resetPwdForm = ref({ password: '' })
const resetPwdRules = computed(() => ({
  password: [
    { required: true, message: t('admin.users.form.required'), trigger: 'blur' },
    { min: 8, message: t('admin.users.form.passwordMin'), trigger: 'blur' },
  ],
}))

const deleteConfirmOpen = ref(false)
const deletingUser = ref<UserPublic | null>(null)

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
    width: 110,
    render: (row) =>
      h(NTag, { size: 'small', type: row.auth_source === 'local' ? 'warning' : 'info', bordered: false },
        { default: () => row.auth_source === 'local' ? 'Local' : 'SSO' }),
  },
  {
    title: t('admin.users.columns.actions'),
    key: 'actions',
    width: 148,
    align: 'center',
    render: (row) =>
      h('div', { style: 'display:flex;gap:4px;justify-content:center' }, [
        h(NButton, {
          size: 'small', quaternary: true, circle: true,
          title: t('admin.users.actions.viewProfile'),
          onClick: () => router.push({ name: 'user-profile', params: { id: row.id } }),
        }, { icon: () => h(NIcon, null, { default: () => h(EyeOutline) }) }),
        row.auth_source === 'local'
          ? h(NButton, {
              size: 'small', quaternary: true, circle: true,
              title: t('admin.users.actions.edit'),
              onClick: () => openEditModal(row),
            }, { icon: () => h(NIcon, null, { default: () => h(CreateOutline) }) })
          : null,
        row.auth_source === 'local'
          ? h(NButton, {
              size: 'small', quaternary: true, circle: true,
              title: t('admin.users.actions.resetPwd'),
              onClick: () => openResetPwdModal(row),
            }, { icon: () => h(NIcon, null, { default: () => h(KeyOutline) }) })
          : null,
        h(NButton, {
          size: 'small', quaternary: true, circle: true, type: 'error',
          title: t('admin.users.actions.delete'),
          onClick: () => openDeleteModal(row),
        }, { icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) }),
      ]),
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

function openCreateModal() {
  createForm.value = { email: '', full_name: '', password: '', role: 'reader' }
  createModalOpen.value = true
}

async function submitCreate() {
  try { await createFormRef.value?.validate() } catch { return }
  savingCreate.value = true
  try {
    const created = await adminCreateLocalUser(createForm.value)
    users.value.unshift(created)
    message.success(t('admin.users.createModal.success'))
    createModalOpen.value = false
  } catch {
    message.error(t('errors.generic'))
  } finally {
    savingCreate.value = false
  }
}

function openEditModal(user: UserPublic) {
  editingUser.value = user
  editForm.value = {
    full_name: user.full_name,
    department: user.department ?? '',
    position: user.position ?? '',
    phone: user.phone ?? '',
  }
  editModalOpen.value = true
}

async function submitEdit() {
  try { await editFormRef.value?.validate() } catch { return }
  if (!editingUser.value) return
  savingEdit.value = true
  try {
    const updated = await adminPatchUserProfile(editingUser.value.id, {
      full_name: editForm.value.full_name,
      department: editForm.value.department || null,
      position: editForm.value.position || null,
      phone: editForm.value.phone || null,
    })
    const idx = users.value.findIndex(u => u.id === editingUser.value!.id)
    if (idx !== -1) users.value[idx] = updated
    message.success(t('admin.users.editModal.success'))
    editModalOpen.value = false
  } catch {
    message.error(t('errors.generic'))
  } finally {
    savingEdit.value = false
  }
}

function openResetPwdModal(user: UserPublic) {
  resetPwdUser.value = user
  resetPwdForm.value = { password: '' }
  resetPwdModalOpen.value = true
}

async function submitResetPwd() {
  try { await resetPwdFormRef.value?.validate() } catch { return }
  if (!resetPwdUser.value) return
  savingResetPwd.value = true
  try {
    await adminResetUserPassword(resetPwdUser.value.id, resetPwdForm.value.password)
    message.success(t('admin.users.resetPwdModal.success'))
    resetPwdModalOpen.value = false
  } catch {
    message.error(t('errors.generic'))
  } finally {
    savingResetPwd.value = false
  }
}

function openDeleteModal(user: UserPublic) {
  deletingUser.value = user
  deleteConfirmOpen.value = true
}

async function confirmDelete() {
  if (!deletingUser.value) return
  try {
    await adminDeleteUser(deletingUser.value.id)
    users.value = users.value.filter(u => u.id !== deletingUser.value!.id)
    message.success(t('admin.users.deleteModal.success'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    deletingUser.value = null
  }
}

onMounted(() => {
  void loadUsers()
})
</script>

<style scoped>
@import '../admin-tabs.css';
</style>
