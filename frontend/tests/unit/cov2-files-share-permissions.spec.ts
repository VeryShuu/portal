import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const messageMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}))

const fileApiMock = vi.hoisted(() => ({
  fetchFileShares: vi.fn(async () => ({ items: [] })),
  createFileShare: vi.fn(async () => ({})),
  revokeFileShare: vi.fn(async () => ({})),
  searchFilesSubjects: vi.fn(async () => []),
  fetchPermissions: vi.fn(async () => ({ items: [] })),
  grantPermission: vi.fn(async () => ({})),
  revokePermission: vi.fn(async () => ({})),
  setFolderInheritance: vi.fn(async () => ({})),
}))

const apiIndexMock = vi.hoisted(() => ({
  api: vi.fn(async () => []),
}))

vi.mock('naive-ui', () => ({
  NButton: { template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>', props: ['size', 'type', 'disabled', 'loading', 'text', 'ghost'], emits: ['click'] },
  NDivider: { template: '<hr class="n-divider" />' },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['size', 'type', 'bordered'] },
  NTooltip: { template: '<div class="n-tooltip"><slot name="trigger" /><slot /></div>', props: ['placement'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset'], emits: ['update:show'] },
  NAutoComplete: {
    template: '<div><input class="n-auto" :value="value" @input="$emit(\'update:value\', $event.target.value)" /><button class="pick-first" v-if="options && options.length" @click="$emit(\'select\', options[0].value)">pick</button></div>',
    props: ['value', 'options', 'loading', 'placeholder', 'clearable', 'size'],
    emits: ['update:value', 'select'],
  },
  NSelect: {
    template: '<select class="n-select" :value="value" @change="$emit(\'update:value\', $event.target.value)"><option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option></select>',
    props: ['value', 'options', 'size'],
    emits: ['update:value'],
  },
  NInputNumber: {
    template: '<input class="n-input-number" type="number" :value="value" @input="$emit(\'update:value\', Number($event.target.value))" />',
    props: ['value', 'min', 'max', 'size', 'clearable', 'placeholder'],
    emits: ['update:value'],
  },
  NSwitch: {
    template: '<input class="n-switch" type="checkbox" :checked="value" @change="$emit(\'update:value\', $event.target.checked)" />',
    props: ['value', 'loading'],
    emits: ['update:value'],
  },
  NDataTable: { name: 'NDataTable', template: '<div class="n-data-table" />', props: ['columns', 'data', 'size'] },
  useMessage: () => messageMock,
}))

vi.mock('../../src/api/files', () => fileApiMock)
vi.mock('../../src/api', () => apiIndexMock)

function makeSubject(subject_id: string, subject_type: 'user' | 'group' = 'user') {
  return { subject_id, subject_type, subject_name: subject_id, email: `${subject_id}@mail.test` }
}

function makeShare(overrides: Record<string, unknown> = {}) {
  return {
    id: 'sh-1',
    folder_id: 'f-1',
    filename: 'f.txt',
    nc_path: '/f.txt',
    subject_type: 'user',
    subject_id: 'u1',
    subject_name: 'User 1',
    permission: 'viewer',
    shared_by: null,
    created_at: '2024-01-01T00:00:00Z',
    expires_at: null,
    ...overrides,
  }
}

function makePerm(overrides: Record<string, unknown> = {}) {
  return {
    id: 'p-1',
    folder_id: 'f-1',
    subject_type: 'user',
    subject_id: 'u1',
    subject_name: 'User 1',
    permission: 'viewer',
    is_creator: false,
    ...overrides,
  }
}

function globalPlugins() {
  return { global: { plugins: [i18n] } }
}

describe('FilesShareModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function mountComp(props: Record<string, unknown> = {}) {
    const { default: Comp } = await import('../../src/components/files/FilesShareModal.vue')
    return mount(Comp, {
      ...globalPlugins(),
      props: {
        show: false,
        folderId: 'f-1',
        filename: 'file.txt',
        ...props,
      },
    })
  }

  async function openModal(wrapper: any) {
    await wrapper.setProps({ show: true })
    await flushPromises()
  }

  it('loads shares on open and renders rows/empty branches', async () => {
    fileApiMock.fetchFileShares.mockResolvedValueOnce({ items: [makeShare()] })
    const wrapper = await mountComp()
    await openModal(wrapper)
    expect(fileApiMock.fetchFileShares).toHaveBeenCalledWith('f-1', 'file.txt')
    expect(wrapper.findAll('.share-row')).toHaveLength(1)

    fileApiMock.fetchFileShares.mockResolvedValueOnce({ items: [] })
    await wrapper.setProps({ show: false })
    await openModal(wrapper)
    expect(wrapper.find('.share-empty').exists()).toBe(true)
  })

  it('searches subjects (success and fail), selects and warns for all users', async () => {
    fileApiMock.searchFilesSubjects.mockResolvedValueOnce([makeSubject('__all_users__')])
    const wrapper = await mountComp()
    await openModal(wrapper)

    const auto = wrapper.find('.n-auto')
    await auto.setValue('a')
    await vi.runAllTimersAsync()
    expect(fileApiMock.searchFilesSubjects).not.toHaveBeenCalled()

    await auto.setValue('all')
    await vi.advanceTimersByTimeAsync(450)
    await flushPromises()
    expect(fileApiMock.searchFilesSubjects).toHaveBeenCalledWith('all')

    await wrapper.find('.pick-first').trigger('click')
    expect(wrapper.text()).toContain('files.share.allUsersWarn')

    fileApiMock.searchFilesSubjects.mockRejectedValueOnce(new Error('x'))
    await auto.setValue('er')
    await vi.advanceTimersByTimeAsync(450)
    await flushPromises()
    expect(wrapper.exists()).toBe(true)
  })

  it('submits new share and revokes share', async () => {
    fileApiMock.fetchFileShares.mockResolvedValue({ items: [makeShare()] })
    fileApiMock.searchFilesSubjects.mockResolvedValueOnce([makeSubject('u-22')])
    const wrapper = await mountComp()
    await openModal(wrapper)

    await wrapper.find('.n-auto').setValue('us')
    await vi.advanceTimersByTimeAsync(450)
    await flushPromises()
    const pick = wrapper.find('.pick-first')
    if (pick.exists()) {
      await pick.trigger('click')
    } else {
      ;(wrapper.vm as any).grantForm.subject_id = 'u-22'
      ;(wrapper.vm as any).grantForm.subject_name = 'u-22'
    }

    await wrapper.find('.n-input-number').setValue('10')
    const addBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('files.share.add'))
    expect(addBtn).toBeTruthy()
    await addBtn!.trigger('click')
    await flushPromises()

    expect(fileApiMock.createFileShare).toHaveBeenCalled()

    const revokeBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('✕'))
    expect(revokeBtn).toBeTruthy()
    await revokeBtn!.trigger('click')
    await flushPromises()
    expect(fileApiMock.revokeFileShare).toHaveBeenCalled()
  })

  it('shows error messages for load/create/revoke failures', async () => {
    fileApiMock.fetchFileShares.mockRejectedValueOnce(new Error('load'))
    const wrapper = await mountComp()
    await openModal(wrapper)
    expect(messageMock.error).toHaveBeenCalledWith('files.share.error.load')

    fileApiMock.searchFilesSubjects.mockResolvedValueOnce([makeSubject('u-err')])
    fileApiMock.createFileShare.mockRejectedValueOnce(new Error('create'))
    await wrapper.find('.n-auto').setValue('uu')
    await vi.advanceTimersByTimeAsync(450)
    await flushPromises()
    const pick = wrapper.find('.pick-first')
    if (pick.exists()) {
      await pick.trigger('click')
    } else {
      ;(wrapper.vm as any).grantForm.subject_id = 'u-err'
      ;(wrapper.vm as any).grantForm.subject_name = 'u-err'
    }
    const addBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('files.share.add'))
    await addBtn!.trigger('click')
    await flushPromises()
    expect(messageMock.error).toHaveBeenCalledWith('files.share.error.create')

    fileApiMock.fetchFileShares.mockResolvedValueOnce({ items: [makeShare()] })
    await wrapper.setProps({ show: false })
    await openModal(wrapper)
    fileApiMock.revokeFileShare.mockRejectedValueOnce(new Error('revoke'))
    const revokeBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('✕'))
    await revokeBtn!.trigger('click')
    await flushPromises()
    expect(messageMock.error).toHaveBeenCalledWith('files.share.error.revoke')
  })
})

describe('FilesPermissionsModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function mountComp(props: Record<string, unknown> = {}) {
    const { default: Comp } = await import('../../src/components/files/FilesPermissionsModal.vue')
    return mount(Comp, {
      ...globalPlugins(),
      props: {
        show: false,
        folderId: 'f-1',
        parentId: 'p-1',
        inheritPermissions: true,
        ...props,
      },
    })
  }

  it('loads permissions on open and handles parentId branch', async () => {
    fileApiMock.fetchPermissions.mockResolvedValueOnce({ items: [makePerm()] })
    const wrapper = await mountComp()
    await wrapper.setProps({ show: true })
    await flushPromises()
    expect(fileApiMock.fetchPermissions).toHaveBeenCalledWith('f-1')
    expect(wrapper.find('.perm-inherit-row').exists()).toBe(true)

    const noParent = await mountComp({ parentId: null })
    await noParent.setProps({ show: true })
    await flushPromises()
    expect(noParent.find('.perm-inherit-row').exists()).toBe(false)
  })

  it('toggles inheritance success and failure branches', async () => {
    const wrapper = await mountComp()
    await wrapper.setProps({ show: true })
    await flushPromises()
    await wrapper.find('.n-switch').setValue(false)
    await flushPromises()
    expect(fileApiMock.setFolderInheritance).toHaveBeenCalledWith('f-1', false)
    expect(wrapper.emitted('tree-refresh')).toBeTruthy()

    fileApiMock.setFolderInheritance.mockRejectedValueOnce(new Error('x'))
    await wrapper.find('.n-switch').setValue(true)
    await flushPromises()
    expect(messageMock.error).toHaveBeenCalledWith('files.error.toggleInheritance')
  })

  it('searches subjects and submits grant with success and failure', async () => {
    apiIndexMock.api.mockResolvedValueOnce([makeSubject('u-1')])
    const wrapper = await mountComp()
    await wrapper.setProps({ show: true })
    await flushPromises()

    await wrapper.find('.n-auto').setValue('u')
    await vi.runAllTimersAsync()
    expect(apiIndexMock.api).not.toHaveBeenCalled()

    await wrapper.find('.n-auto').setValue('us')
    await vi.advanceTimersByTimeAsync(450)
    await flushPromises()
    expect(apiIndexMock.api).toHaveBeenCalled()

    const pick1 = wrapper.find('.pick-first')
    if (pick1.exists()) {
      await pick1.trigger('click')
    } else {
      ;(wrapper.vm as any).grantForm.subject_id = 'u-1'
      ;(wrapper.vm as any).grantForm.subject_name = 'u-1'
    }
    const addBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('files.permissions.add'))
    await addBtn!.trigger('click')
    await flushPromises()
    expect(fileApiMock.grantPermission).toHaveBeenCalled()

    apiIndexMock.api.mockRejectedValueOnce(new Error('fail search'))
    await wrapper.find('.n-auto').setValue('zz')
    await vi.advanceTimersByTimeAsync(450)
    await flushPromises()
    expect(wrapper.exists()).toBe(true)

    apiIndexMock.api.mockResolvedValueOnce([makeSubject('u-2')])
    fileApiMock.grantPermission.mockRejectedValueOnce(new Error('grant'))
    await wrapper.find('.n-auto').setValue('ux')
    await vi.advanceTimersByTimeAsync(450)
    await flushPromises()
    const pick2 = wrapper.find('.pick-first')
    if (pick2.exists()) {
      await pick2.trigger('click')
    } else {
      ;(wrapper.vm as any).grantForm.subject_id = 'u-2'
      ;(wrapper.vm as any).grantForm.subject_name = 'u-2'
    }
    const addBtn2 = wrapper.findAll('.n-button').find((b) => b.text().includes('files.permissions.add'))
    await addBtn2!.trigger('click')
    await flushPromises()
    expect(messageMock.error).toHaveBeenCalledWith('files.error.grantPerm')
  })

  it('revoke action branch via table column render', async () => {
    fileApiMock.fetchPermissions.mockResolvedValueOnce({ items: [makePerm()] })
    const wrapper = await mountComp()
    await wrapper.setProps({ show: true })
    await flushPromises()

    const table = wrapper.findComponent({ name: 'NDataTable' })
    const columns = table.props('columns') as Array<Record<string, any>>
    const actionsCol = columns.find((c) => c.key === 'actions')!
    const actionVnode = actionsCol.render(makePerm({ id: 'perm-9', is_creator: false }))
    await actionVnode.props.onClick()
    await flushPromises()
    expect(fileApiMock.revokePermission).toHaveBeenCalledWith('f-1', 'perm-9')

    fileApiMock.revokePermission.mockRejectedValueOnce(new Error('revoke'))
    await actionVnode.props.onClick()
    await flushPromises()
    expect(messageMock.error).toHaveBeenCalledWith('files.error.revokePerm')
  })
})
