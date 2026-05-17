<template>
  <div>
    <div class="tab-toolbar">
      <n-input
        v-model:value="userSearch"
        :placeholder="t('common.search')"
        clearable
        style="max-width:260px"
      >
        <template #prefix>
          <n-icon><SearchOutline /></n-icon>
        </template>
      </n-input>
      <n-button
        type="primary"
        @click="openCreateModal"
      >
        <template #icon>
          <n-icon><AddOutline /></n-icon>
        </template>
        {{ t('admin.users.addLocal') }}
      </n-button>
      <n-button
        :loading="syncing"
        @click="syncUsers"
      >
        <template #icon>
          <n-icon><SyncOutline /></n-icon>
        </template>
        {{ syncing ? t('admin.users.syncing') : t('admin.users.syncFromKeycloak') }}
      </n-button>
    </div>

    <n-data-table
      :columns="userColumns"
      :data="users"
      :loading="loadingUsers"
      :pagination="tablePagination"
      :remote="true"
      :row-key="(row: UserPublic) => row.id"
      striped
      class="data-table"
      @update:page="handlePageChange"
    />

    <n-modal
      v-model:show="createModalOpen"
      :title="t('admin.users.createModal.title')"
      preset="card"
      style="width:480px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        label-placement="top"
      >
        <n-form-item
          :label="t('admin.users.form.email')"
          path="email"
        >
          <n-input
            v-model:value="createForm.email"
            :placeholder="t('admin.users.form.emailPlaceholder')"
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.users.form.fullName')"
          path="full_name"
        >
          <n-input
            v-model:value="createForm.full_name"
            :placeholder="t('admin.users.form.fullNamePlaceholder')"
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.users.form.password')"
          path="password"
        >
          <n-input
            v-model:value="createForm.password"
            type="password"
            show-password-on="click"
            :placeholder="t('admin.users.form.passwordPlaceholder')"
          />
        </n-form-item>
        <n-form-item
          :label="t('admin.users.columns.role')"
          path="role"
        >
          <n-select
            v-model:value="createForm.role"
            :options="roleOptions"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="createModalOpen = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="savingCreate"
            @click="submitCreate"
          >
            {{ t('common.save') }}
          </n-button>
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
      <n-form
        ref="editFormRef"
        :model="editForm"
        :rules="editRules"
        label-placement="top"
      >
        <n-form-item
          :label="t('admin.users.form.fullName')"
          path="full_name"
        >
          <n-input
            v-model:value="editForm.full_name"
            :placeholder="t('admin.users.form.fullNamePlaceholder')"
          />
        </n-form-item>
        <n-form-item :label="t('admin.users.form.department')">
          <n-input
            v-model:value="editForm.department"
            :placeholder="t('admin.users.form.departmentPlaceholder')"
            clearable
          />
        </n-form-item>
        <n-form-item :label="t('admin.users.form.position')">
          <n-input
            v-model:value="editForm.position"
            :placeholder="t('admin.users.form.positionPlaceholder')"
            clearable
          />
        </n-form-item>
        <n-form-item :label="t('admin.users.form.phone')">
          <n-input
            v-model:value="editForm.phone"
            :placeholder="t('admin.users.form.phonePlaceholder')"
            clearable
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="editModalOpen = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="savingEdit"
            @click="submitEdit"
          >
            {{ t('common.save') }}
          </n-button>
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
      <n-form
        ref="resetPwdFormRef"
        :model="resetPwdForm"
        :rules="resetPwdRules"
        label-placement="top"
      >
        <n-form-item
          :label="t('admin.users.form.newPassword')"
          path="password"
        >
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
          <n-button @click="resetPwdModalOpen = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="savingResetPwd"
            @click="submitResetPwd"
          >
            {{ t('common.save') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  NDataTable, NButton, NInput, NIcon, NTag, NSelect, NModal, NForm, NFormItem,
  useMessage, type DataTableColumns,
} from 'naive-ui'
import { useConfirmDialog } from '../../../composables/useConfirmDialog'
import {
  SearchOutline, SyncOutline, AddOutline, CreateOutline, TrashOutline, KeyOutline, EyeOutline,
} from '@vicons/ionicons5'
import {
  changeUserRole, syncUsersFromKeycloak,
  adminCreateLocalUser, adminPatchUserProfile, adminResetUserPassword, adminDeleteUser,
  type UserPublic,
} from '../../../api/users'
import { useAdminUsersQuery } from '../../../queries/admin'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../../queries/keys'

const { t } = useI18n()
const message = useMessage()
const { confirm } = useConfirmDialog()
const router = useRouter()
const qc = useQueryClient()

const PAGE_SIZE = 50

const currentPage = ref(1)
const syncing = ref(false)
const userSearch = ref('')

let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null

const queryParams = computed(() => ({
  q: userSearch.value.trim() || undefined,
  page: currentPage.value,
  page_size: PAGE_SIZE,
}))

const { data: usersData, isLoading: loadingUsers } = useAdminUsersQuery(queryParams)
const users = computed(() => usersData.value?.items ?? [])
const total = computed(() => usersData.value?.total ?? 0)

const tablePagination = computed(() => ({
  page: currentPage.value,
  pageSize: PAGE_SIZE,
  itemCount: total.value,
  showSizePicker: false,
  prefix: ({ itemCount }: { itemCount: number | undefined }) => t('admin.users.totalCount', { count: itemCount ?? 0 }),
}))

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
    title: t('admin.users.columns.lastLoginAt'),
    key: 'last_login_at',
    width: 160,
    render: (row) => row.last_login_at ? new Date(row.last_login_at).toLocaleString() : '—',
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

function handlePageChange(page: number) {
  currentPage.value = page
}

watch(userSearch, () => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    currentPage.value = 1
  }, 350)
})

async function handleRoleChange(user: UserPublic, role: string) {
  try {
    await changeUserRole(user.id, role)
    message.success(t('admin.users.roleChanged'))
    qc.invalidateQueries({ queryKey: queryKeys.admin.users() })
  } catch {
    message.error(t('errors.generic'))
  }
}

async function syncUsers() {
  syncing.value = true
  try {
    await syncUsersFromKeycloak()
    message.success(t('admin.users.syncOk'))
    qc.invalidateQueries({ queryKey: queryKeys.admin.users() })
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
    await adminCreateLocalUser(createForm.value)
    qc.invalidateQueries({ queryKey: queryKeys.admin.users() })
    message.success(t('admin.users.createModal.success'))
    createModalOpen.value = false
  } catch (err: unknown) {
    const detail = (err as { data?: { detail?: string } })?.data?.detail
    message.error(typeof detail === 'string' ? detail : t('errors.generic'))
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
    await adminPatchUserProfile(editingUser.value.id, {
      full_name: editForm.value.full_name,
      department: editForm.value.department || null,
      position: editForm.value.position || null,
      phone: editForm.value.phone || null,
    })
    qc.invalidateQueries({ queryKey: queryKeys.admin.users() })
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

async function openDeleteModal(user: UserPublic) {
  const ok = await confirm({
    title: t('admin.users.deleteModal.title', { name: user.full_name }),
    content: t('admin.users.deleteModal.hint'),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
  })
  if (!ok) return
  try {
    await adminDeleteUser(user.id)
    qc.invalidateQueries({ queryKey: queryKeys.admin.users() })
    message.success(t('admin.users.deleteModal.success'))
  } catch {
    message.error(t('errors.generic'))
  }
}


</script>

<style scoped>
@import '../admin-tabs.css';
</style>
