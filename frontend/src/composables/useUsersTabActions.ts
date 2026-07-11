import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useQueryClient } from '@tanstack/vue-query'
import { useConfirmDialog } from './useConfirmDialog'
import {
  changeUserRole, syncUsersFromKeycloak,
  adminCreateLocalUser, adminPatchUserProfile, adminResetUserPassword, adminDeleteUser,
  type UserPublic,
} from '../api/users'
import { queryKeys } from '../queries/keys'
import { parseApiError } from '../utils/parseApiError'

export function useUsersTabActions() {
  const { t } = useI18n()
  const message = useMessage()
  const { confirm } = useConfirmDialog()
  const qc = useQueryClient()

  const roleOptions = computed(() => [
    { label: t('admin.users.role.reader'), value: 'reader' },
    { label: t('admin.users.role.editor'), value: 'editor' },
    { label: t('admin.users.role.admin'), value: 'admin' },
  ])

  const syncing = ref(false)

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

  async function handleRoleChange(user: UserPublic, role: string) {
    try {
      await changeUserRole(user.id, role)
      message.success(t('admin.users.roleChanged'))
      qc.invalidateQueries({ queryKey: queryKeys.admin.users() })
    } catch (e) {
      message.error(parseApiError(e, t))
    }
  }

  async function syncUsers() {
    syncing.value = true
    try {
      await syncUsersFromKeycloak()
      message.success(t('admin.users.syncOk'))
      qc.invalidateQueries({ queryKey: queryKeys.admin.users() })
    } catch (e) {
      message.error(parseApiError(e, t))
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
      message.error(parseApiError(err, t))
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
    } catch (e) {
      message.error(parseApiError(e, t))
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
    } catch (e) {
      message.error(parseApiError(e, t))
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
    } catch (e) {
      message.error(parseApiError(e, t))
    }
  }

  return {
    roleOptions, syncing,
    createModalOpen, savingCreate, createFormRef, createForm, createRules,
    editModalOpen, savingEdit, editFormRef, editForm, editRules,
    resetPwdModalOpen, savingResetPwd, resetPwdFormRef, resetPwdForm, resetPwdRules,
    handleRoleChange, syncUsers, openCreateModal, submitCreate,
    openEditModal, submitEdit,
    openResetPwdModal, submitResetPwd,
    openDeleteModal,
  }
}
