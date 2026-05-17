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
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NDataTable, NButton, NInput, NIcon, NModal, NForm, NFormItem, NSelect,
} from 'naive-ui'
import {
  SearchOutline, SyncOutline, AddOutline,
} from '@vicons/ionicons5'
import { type UserPublic } from '../../../api/users'
import { useAdminUsersQuery } from '../../../queries/admin'
import { useUsersTabActions } from '../../../composables/useUsersTabActions'
import { useUsersTableColumns } from '../../../composables/useUsersTableColumns'

const { t } = useI18n()

const PAGE_SIZE = 50

const currentPage = ref(1)
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

const {
  roleOptions, syncing,
  createModalOpen, savingCreate, createFormRef, createForm, createRules,
  editModalOpen, savingEdit, editFormRef, editForm, editRules,
  resetPwdModalOpen, savingResetPwd, resetPwdFormRef, resetPwdForm, resetPwdRules,
  handleRoleChange, syncUsers, openCreateModal, submitCreate,
  openEditModal, submitEdit,
  openResetPwdModal, submitResetPwd,
  openDeleteModal,
} = useUsersTabActions()

const { userColumns } = useUsersTableColumns(
  roleOptions,
  handleRoleChange,
  openEditModal,
  openResetPwdModal,
  openDeleteModal,
)

function handlePageChange(page: number) {
  currentPage.value = page
}

watch(userSearch, () => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    currentPage.value = 1
  }, 350)
})

</script>

<style scoped>
@import '../admin-tabs.css';
</style>
