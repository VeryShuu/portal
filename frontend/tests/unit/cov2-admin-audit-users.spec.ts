import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import { ref } from 'vue'

const {
  useQueryMock,
  useInfiniteQueryMock,
  queryClientMock,
  messageMock,
  ofetchMock,
  handleRoleChangeMock,
  syncUsersMock,
  openCreateModalMock,
  submitCreateMock,
  openEditModalMock,
  submitEditMock,
  openResetPwdModalMock,
  submitResetPwdMock,
  openDeleteModalMock,
} = vi.hoisted(() => ({
  useQueryMock: vi.fn(),
  useInfiniteQueryMock: vi.fn(),
  queryClientMock: {
    invalidateQueries: vi.fn().mockResolvedValue(undefined),
    removeQueries: vi.fn(),
    setQueryData: vi.fn(),
  },
  messageMock: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ofetchMock: vi.fn(),
  handleRoleChangeMock: vi.fn(),
  syncUsersMock: vi.fn(),
  openCreateModalMock: vi.fn(),
  submitCreateMock: vi.fn(),
  openEditModalMock: vi.fn(),
  submitEditMock: vi.fn(),
  openResetPwdModalMock: vi.fn(),
  submitResetPwdMock: vi.fn(),
  openDeleteModalMock: vi.fn(),
}))

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: { template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /><slot name="icon" /></button>', props: ['type', 'size', 'disabled', 'loading', 'ghost', 'quaternary', 'tertiary', 'circle', 'title'], emits: ['click'] },
  NButtonGroup: { template: '<div><slot /></div>' },
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NEmpty: { template: '<div class="n-empty"><slot /></div>', props: ['description'] },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'title', 'showIcon', 'closable'] },
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'size'], emits: ['update:value'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color', 'component'] },
  NCard: { template: '<div class="n-card"><slot /></div>', props: ['bordered', 'size', 'title'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type', 'maxlength', 'size', 'clearable', 'status'],
    emits: ['update:value'],
  },
  NSelect: {
    template: '<select :value="value" @change="$emit(\'update:value\', $event.target.value)"><option v-for="o in options || []" :key="o.value" :value="o.value">{{ o.label }}</option></select>',
    props: ['value', 'options', 'placeholder', 'multiple', 'clearable'],
    emits: ['update:value'],
  },
  NPagination: { template: '<div class="n-pagination" />', props: ['page', 'pageCount', 'pageSize'], emits: ['update:page'] },
  NRadioGroup: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NRadioButton: { template: '<label><slot /></label>', props: ['value', 'label'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /><slot name="footer" /></div>', props: ['show', 'title', 'preset'], emits: ['update:show'] },
  NDrawer: { template: '<div class="n-drawer" v-if="show"><slot /></div>', props: ['show', 'width', 'placement'], emits: ['update:show'] },
  NDrawerContent: { template: '<div><slot /></div>', props: ['title', 'closable'] },
  NForm: { template: '<form><slot /></form>', props: ['model', 'rules'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path'] },
  NCheckbox: { template: '<input type="checkbox" :checked="checked" @change="$emit(\'update:checked\', !checked)" />', props: ['checked'], emits: ['update:checked'] },
  NSwitch: { template: '<input type="checkbox" :checked="value" @change="$emit(\'update:value\', !value)" />', props: ['value'], emits: ['update:value'] },
  NDataTable: {
    template: '<div class="n-data-table" @click="$emit(\'update:page\', 2)" />',
    props: ['data', 'columns', 'pagination', 'loading', 'remote'],
    emits: ['update:page'],
  },
  NSpace: { template: '<div><slot /></div>', props: ['justify', 'align', 'size', 'vertical'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'closable', 'bordered'] },
  NTooltip: { template: '<div><slot /><slot name="trigger" /></div>' },
  NPopconfirm: { template: '<div><slot /><slot name="trigger" /></div>' },
  NDivider: { template: '<hr />' },
  NText: { template: '<span><slot /></span>', props: ['depth', 'type'] },
  NDynamicTags: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NUpload: { template: '<div><slot /></div>', props: ['multiple', 'showFileList', 'fileList', 'customRequest'] },
  NColorPicker: { template: '<input type="color" />', props: ['value'], emits: ['update:value'] },
  NInputNumber: { template: '<input type="number" :value="value" @input="$emit(\'update:value\', Number($event.target.value))" />', props: ['value', 'min', 'max'], emits: ['update:value'] },
  NScrollbar: { template: '<div><slot /></div>' },
  NCollapse: { template: '<div><slot /></div>' },
  NCollapseItem: { template: '<div><slot /></div>', props: ['title', 'name'] },
  NCode: { template: '<pre><slot /></pre>', props: ['code', 'language'] },
  NDatePicker: { template: '<input type="date" />', props: ['value', 'type', 'placeholder'], emits: ['update:value'] },
  NSkeleton: { template: '<div class="n-skeleton" />', props: ['text', 'repeat'] },
  NTimePicker: { template: '<input type="time" />', props: ['value'], emits: ['update:value'] },
  NList: { template: '<ul><slot /></ul>' },
  NListItem: { template: '<li><slot /></li>' },
  NThing: { template: '<div><slot /></div>', props: ['title', 'description'] },
  NAvatar: { template: '<div class="n-avatar" />', props: ['src', 'size', 'round'] },
  NBadge: { template: '<div><slot /></div>', props: ['value', 'max'] },
  NDescriptions: { template: '<div><slot /></div>', props: ['column', 'bordered'] },
  NDescriptionsItem: { template: '<div><slot /></div>', props: ['label'] },
  useMessage: () => messageMock,
  useDialog: () => ({ warning: vi.fn(), error: vi.fn(), success: vi.fn() }),
  useLoadingBar: () => ({ start: vi.fn(), finish: vi.fn(), error: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/admin', name: 'admin' })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: useQueryMock,
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: { value: false }, isError: { value: false } })),
  useQueryClient: vi.fn(() => queryClientMock),
  useInfiniteQuery: useInfiniteQueryMock,
  keepPreviousData: undefined,
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({ data: {} }),
  apiUpload: vi.fn().mockResolvedValue({ data: {} }),
  BASE_URL: '/api/v1',
}))

vi.mock('ofetch', () => ({
  ofetch: ofetchMock,
}))

vi.mock('../../src/composables/useUsersTabActions', async () => {
  const { ref } = await import('vue')
  return {
    useUsersTabActions: () => ({
      roleOptions: ref([{ label: 'admin', value: 'admin' }]),
      syncing: ref(false),
      createModalOpen: ref(false),
      savingCreate: ref(false),
      createFormRef: ref(),
      createForm: ref({ email: '', full_name: '', password: '', role: 'user' }),
      createRules: ref({}),
      editModalOpen: ref(false),
      savingEdit: ref(false),
      editFormRef: ref(),
      editForm: ref({ full_name: '', department: '', position: '', phone: '' }),
      editRules: ref({}),
      resetPwdModalOpen: ref(false),
      savingResetPwd: ref(false),
      resetPwdFormRef: ref(),
      resetPwdForm: ref({ password: '' }),
      resetPwdRules: ref({}),
      handleRoleChange: handleRoleChangeMock,
      syncUsers: syncUsersMock,
      openCreateModal: openCreateModalMock,
      submitCreate: submitCreateMock,
      openEditModal: openEditModalMock,
      submitEdit: submitEditMock,
      openResetPwdModal: openResetPwdModalMock,
      submitResetPwd: submitResetPwdMock,
      openDeleteModal: openDeleteModalMock,
    }),
  }
})

vi.mock('../../src/composables/useUsersTableColumns', () => ({
  useUsersTableColumns: () => ({
    userColumns: ref([
      { title: 'Email', key: 'email' },
      { title: 'Actions', key: 'actions' },
    ]),
  }),
}))

vi.mock('@vicons/ionicons5', () => ({
  DownloadOutline: { template: '<span />' },
  SearchOutline: { template: '<span />' },
  SyncOutline: { template: '<span />' },
  AddOutline: { template: '<span />' },
}))
vi.mock('@vicons/fluent', () => ({}))

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
  },
}

function qResult(data: unknown, options?: { isLoading?: boolean; isError?: boolean }) {
  return {
    data: ref(data),
    isLoading: ref(options?.isLoading ?? false),
    isFetching: ref(false),
    isError: ref(options?.isError ?? false),
    error: ref(null),
    refetch: vi.fn(),
  }
}

describe('cov2 admin tabs: audit + users', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    useInfiniteQueryMock.mockReturnValue({ data: ref({ pages: [] }), isLoading: ref(false), fetchNextPage: vi.fn(), hasNextPage: ref(false) })
  })

  it('AuditTab mounts with loading and empty data', async () => {
    useQueryMock
      .mockReturnValueOnce(qResult(undefined, { isLoading: true }))
      .mockReturnValueOnce(qResult(null, { isLoading: true }))
      .mockReturnValueOnce(qResult({ items: [], total: null }, { isLoading: true }))

    const Component = (await import('../../src/pages/admin/tabs/AuditTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
  })

  it('AuditTab shows queue/total branches and rejects invalid user filter', async () => {
    useQueryMock
      .mockReturnValueOnce(qResult(['login', 'logout']))
      .mockReturnValueOnce(qResult({ pending: 3, processing: 1 }))
      .mockReturnValueOnce(qResult({
        items: [{ id: '1', created_at: '2026-01-01T00:00:00.000Z', event_type: 'login', user_email: 'a@b.c', resource_type: 'doc', resource_id: '5', resource_title: 'Title', ip_address: '127.0.0.1', metadata: { ok: true } }],
        total: 12,
      }))

    const Component = (await import('../../src/pages/admin/tabs/AuditTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.text()).toContain('admin.audit.totalRows')

    const userIdInput = wrapper.findAll('input')[0]
    await userIdInput.setValue('not-a-uuid')
    await flushPromises()

    const applyBtn = wrapper.findAll('button')[0]
    await applyBtn.trigger('click')
    await flushPromises()

    expect(messageMock.error).toHaveBeenCalled()
  })

  it('AuditTab handles export csv error branch', async () => {
    useQueryMock
      .mockReturnValueOnce(qResult([]))
      .mockReturnValueOnce(qResult(null))
      .mockReturnValueOnce(qResult({ items: [], total: 0 }))
    ofetchMock.mockRejectedValue(new Error('network'))

    const Component = (await import('../../src/pages/admin/tabs/AuditTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    const exportBtn = wrapper.findAll('button')[2]
    await exportBtn.trigger('click')
    await flushPromises()

    expect(messageMock.error).toHaveBeenCalled()
  })

  it('UsersTab mounts with loading then calls open create action', async () => {
    useQueryMock.mockReturnValueOnce(qResult({ items: [], total: 0 }, { isLoading: true }))

    const Component = (await import('../../src/pages/admin/tabs/UsersTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.exists()).toBe(true)

    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()

    expect(openCreateModalMock).toHaveBeenCalled()
  })

  it('UsersTab renders loaded users scenario and handles table page event', async () => {
    useQueryMock.mockReturnValueOnce(qResult({
      items: [{ id: 'u1', email: 'user@site.local', full_name: 'User One', role: 'user' }],
      total: 1,
    }))

    const Component = (await import('../../src/pages/admin/tabs/UsersTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.text()).toContain('admin.users.addLocal')

    await wrapper.find('.n-data-table').trigger('click')
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
  })
})
