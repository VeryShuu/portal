import { describe, it, expect, beforeEach, vi } from 'vitest'

const mockSuccess = vi.fn()
const mockError = vi.fn()
const mockInvalidateQueries = vi.fn()
const mockConfirm = vi.fn()

const mockChangeUserRole = vi.fn()
const mockSyncUsersFromKeycloak = vi.fn()
const mockAdminCreateLocalUser = vi.fn()
const mockAdminPatchUserProfile = vi.fn()
const mockAdminResetUserPassword = vi.fn()
const mockAdminDeleteUser = vi.fn()
const mockParseApiError = vi.fn(() => 'parsed-error')

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('naive-ui', () => ({ useMessage: () => ({ success: mockSuccess, error: mockError }) }))
vi.mock('@tanstack/vue-query', () => ({ useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }) }))
vi.mock('../../src/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: mockConfirm }) }))
vi.mock('../../src/queries/keys', () => ({ queryKeys: { admin: { users: () => ['admin', 'users'] } } }))
vi.mock('../../src/api/users', () => ({
  changeUserRole: mockChangeUserRole,
  syncUsersFromKeycloak: mockSyncUsersFromKeycloak,
  adminCreateLocalUser: mockAdminCreateLocalUser,
  adminPatchUserProfile: mockAdminPatchUserProfile,
  adminResetUserPassword: mockAdminResetUserPassword,
  adminDeleteUser: mockAdminDeleteUser,
}))
vi.mock('../../src/utils/parseApiError', () => ({ parseApiError: mockParseApiError }))

const user = {
  id: 'u1',
  email: 'u1@example.com',
  full_name: 'User One',
  role: 'reader',
  department: null,
  position: null,
  phone: null,
}

describe('useUsersTabActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
  })

  it('exposes role options', async () => {
    const { useUsersTabActions } = await import('../../src/composables/useUsersTabActions')
    const state = useUsersTabActions()
    expect(state.roleOptions.value).toEqual([
      { label: 'admin.users.role.reader', value: 'reader' },
      { label: 'admin.users.role.editor', value: 'editor' },
      { label: 'admin.users.role.admin', value: 'admin' },
    ])
  })

  it('handleRoleChange covers success and catch', async () => {
    const { useUsersTabActions } = await import('../../src/composables/useUsersTabActions')
    const state = useUsersTabActions()

    mockChangeUserRole.mockResolvedValueOnce(undefined)
    await state.handleRoleChange(user as any, 'admin')
    expect(mockChangeUserRole).toHaveBeenCalledWith('u1', 'admin')
    expect(mockSuccess).toHaveBeenCalledWith('admin.users.roleChanged')
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['admin', 'users'] })

    mockChangeUserRole.mockRejectedValueOnce(new Error('x'))
    await state.handleRoleChange(user as any, 'editor')
    expect(mockError).toHaveBeenCalledWith('errors.generic')
  })

  it('syncUsers covers success/catch/finally', async () => {
    const { useUsersTabActions } = await import('../../src/composables/useUsersTabActions')
    const state = useUsersTabActions()

    mockSyncUsersFromKeycloak.mockResolvedValueOnce(undefined)
    await state.syncUsers()
    expect(mockSuccess).toHaveBeenCalledWith('admin.users.syncOk')
    expect(state.syncing.value).toBe(false)

    mockSyncUsersFromKeycloak.mockRejectedValueOnce(new Error('x'))
    await state.syncUsers()
    expect(mockError).toHaveBeenCalledWith('errors.generic')
    expect(state.syncing.value).toBe(false)
  })

  it('openCreateModal resets form and submitCreate covers validate guard', async () => {
    const { useUsersTabActions } = await import('../../src/composables/useUsersTabActions')
    const state = useUsersTabActions()

    state.createForm.value = { email: 'old', full_name: 'old', password: 'old', role: 'admin' } as any
    state.openCreateModal()
    expect(state.createModalOpen.value).toBe(true)
    expect(state.createForm.value).toEqual({ email: '', full_name: '', password: '', role: 'reader' })

    state.createFormRef.value = { validate: vi.fn().mockRejectedValueOnce(new Error('invalid')) }
    await state.submitCreate()
    expect(mockAdminCreateLocalUser).not.toHaveBeenCalled()
  })

  it('submitCreate covers success and error(parseApiError)', async () => {
    const { useUsersTabActions } = await import('../../src/composables/useUsersTabActions')
    const state = useUsersTabActions()

    const createPayload = { email: 'e@x', full_name: 'Name', password: 'pass12345', role: 'editor' }
    state.createForm.value = createPayload as any
    state.createFormRef.value = { validate: vi.fn().mockResolvedValue(undefined) }
    mockAdminCreateLocalUser.mockResolvedValueOnce(undefined)
    await state.submitCreate()
    expect(mockAdminCreateLocalUser).toHaveBeenCalledWith(createPayload)
    expect(mockSuccess).toHaveBeenCalledWith('admin.users.createModal.success')
    expect(state.createModalOpen.value).toBe(false)
    expect(state.savingCreate.value).toBe(false)

    state.createModalOpen.value = true
    state.createFormRef.value = { validate: vi.fn().mockResolvedValue(undefined) }
    mockAdminCreateLocalUser.mockRejectedValueOnce(new Error('dup'))
    await state.submitCreate()
    expect(mockParseApiError).toHaveBeenCalled()
    expect(mockError).toHaveBeenCalledWith('parsed-error')
    expect(state.savingCreate.value).toBe(false)
  })

  it('openEditModal maps nullable fields and submitEdit covers all branches', async () => {
    const { useUsersTabActions } = await import('../../src/composables/useUsersTabActions')
    const state = useUsersTabActions()

    state.openEditModal(user as any)
    expect(state.editModalOpen.value).toBe(true)
    expect(state.editForm.value).toEqual({ full_name: 'User One', department: '', position: '', phone: '' })

    state.editFormRef.value = { validate: vi.fn().mockRejectedValueOnce(new Error('invalid')) }
    await state.submitEdit()
    expect(mockAdminPatchUserProfile).not.toHaveBeenCalled()

    state.editFormRef.value = { validate: vi.fn().mockResolvedValue(undefined) }
    state.openEditModal({ ...user, department: 'IT', position: 'Lead', phone: '123' } as any)
    mockAdminPatchUserProfile.mockResolvedValueOnce(undefined)
    await state.submitEdit()
    expect(mockAdminPatchUserProfile).toHaveBeenCalledWith('u1', {
      full_name: 'User One',
      department: 'IT',
      position: 'Lead',
      phone: '123',
    })
    expect(mockSuccess).toHaveBeenCalledWith('admin.users.editModal.success')
    expect(state.editModalOpen.value).toBe(false)
    expect(state.savingEdit.value).toBe(false)

    state.editFormRef.value = { validate: vi.fn().mockResolvedValue(undefined) }
    state.openEditModal(user as any)
    mockAdminPatchUserProfile.mockRejectedValueOnce(new Error('x'))
    await state.submitEdit()
    expect(mockError).toHaveBeenCalledWith('errors.generic')

    const { useUsersTabActions: useUsersTabActions2 } = await import('../../src/composables/useUsersTabActions')
    const stateNoEditing = useUsersTabActions2()
    stateNoEditing.editFormRef.value = { validate: vi.fn().mockResolvedValue(undefined) }
    await stateNoEditing.submitEdit()
    expect(mockAdminPatchUserProfile).toHaveBeenCalledTimes(2)
  })

  it('openResetPwdModal and submitResetPwd cover all branches', async () => {
    const { useUsersTabActions } = await import('../../src/composables/useUsersTabActions')
    const state = useUsersTabActions()

    state.openResetPwdModal(user as any)
    expect(state.resetPwdModalOpen.value).toBe(true)
    expect(state.resetPwdForm.value).toEqual({ password: '' })

    state.resetPwdFormRef.value = { validate: vi.fn().mockRejectedValueOnce(new Error('invalid')) }
    await state.submitResetPwd()
    expect(mockAdminResetUserPassword).not.toHaveBeenCalled()

    state.resetPwdFormRef.value = { validate: vi.fn().mockResolvedValue(undefined) }
    state.resetPwdForm.value.password = 'pass12345'
    mockAdminResetUserPassword.mockResolvedValueOnce(undefined)
    await state.submitResetPwd()
    expect(mockAdminResetUserPassword).toHaveBeenCalledWith('u1', 'pass12345')
    expect(mockSuccess).toHaveBeenCalledWith('admin.users.resetPwdModal.success')
    expect(state.resetPwdModalOpen.value).toBe(false)

    state.openResetPwdModal(user as any)
    state.resetPwdFormRef.value = { validate: vi.fn().mockResolvedValue(undefined) }
    mockAdminResetUserPassword.mockRejectedValueOnce(new Error('x'))
    await state.submitResetPwd()
    expect(mockError).toHaveBeenCalledWith('errors.generic')

    const { useUsersTabActions: useUsersTabActions2 } = await import('../../src/composables/useUsersTabActions')
    const stateNoUser = useUsersTabActions2()
    stateNoUser.resetPwdFormRef.value = { validate: vi.fn().mockResolvedValue(undefined) }
    await stateNoUser.submitResetPwd()
    expect(mockAdminResetUserPassword).toHaveBeenCalledTimes(2)
  })

  it('openDeleteModal covers confirm reject, success and catch', async () => {
    const { useUsersTabActions } = await import('../../src/composables/useUsersTabActions')
    const state = useUsersTabActions()

    mockConfirm.mockResolvedValueOnce(false)
    await state.openDeleteModal(user as any)
    expect(mockAdminDeleteUser).not.toHaveBeenCalled()

    mockConfirm.mockResolvedValueOnce(true)
    mockAdminDeleteUser.mockResolvedValueOnce(undefined)
    await state.openDeleteModal(user as any)
    expect(mockAdminDeleteUser).toHaveBeenCalledWith('u1')
    expect(mockSuccess).toHaveBeenCalledWith('admin.users.deleteModal.success')

    mockConfirm.mockResolvedValueOnce(true)
    mockAdminDeleteUser.mockRejectedValueOnce(new Error('x'))
    await state.openDeleteModal(user as any)
    expect(mockError).toHaveBeenCalledWith('errors.generic')
  })
})
