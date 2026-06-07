import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const fetchPermissionsMock = vi.fn()
const grantPermissionMock = vi.fn()
const revokePermissionMock = vi.fn()
const searchSubjectsMock = vi.fn()

const message = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}

vi.mock('naive-ui', () => ({
  NButton: { template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'disabled', 'loading', 'ghost', 'quaternary', 'tertiary', 'circle', 'title'], emits: ['click'] },
  NButtonGroup: { template: '<div><slot /></div>' },
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NEmpty: { template: '<div class="n-empty"><slot /></div>', props: ['description'] },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'title', 'showIcon', 'closable'] },
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'size'], emits: ['update:value'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color', 'component'] },
  NCard: { template: '<div class="n-card"><slot /></div>', props: ['bordered', 'size', 'title'] },
  NInput: { template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />', props: ['value', 'placeholder', 'type', 'maxlength', 'size', 'clearable'], emits: ['update:value'] },
  NSelect: { template: '<select class="n-select" :value="value" @change="$emit(\'update:value\', $event.target.value)"><slot /></select>', props: ['value', 'options', 'placeholder', 'multiple', 'clearable'], emits: ['update:value'] },
  NPagination: { template: '<div class="n-pagination" />', props: ['page', 'pageCount', 'pageSize'], emits: ['update:page'] },
  NRadioGroup: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NRadioButton: { template: '<label><slot /></label>', props: ['value', 'label'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset', 'maskClosable'], emits: ['update:show'] },
  NDrawer: { template: '<div class="n-drawer" v-if="show"><slot /></div>', props: ['show', 'width', 'placement'], emits: ['update:show'] },
  NDrawerContent: { template: '<div><slot /></div>', props: ['title', 'closable'] },
  NForm: { template: '<form><slot /></form>', props: ['model', 'rules'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path'] },
  NCheckbox: { template: '<input type="checkbox" />', props: ['checked'], emits: ['update:checked'] },
  NSwitch: { template: '<input type="checkbox" />', props: ['value'], emits: ['update:value'] },
  NDataTable: { template: '<div class="n-data-table" />', props: ['data', 'columns', 'pagination', 'loading', 'size'] },
  NSpace: { template: '<div><slot /></div>', props: ['justify', 'align', 'size', 'vertical'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'closable', 'bordered'] },
  NTooltip: { template: '<div><slot /><slot name="trigger" /></div>' },
  NPopconfirm: { template: '<div><slot /><slot name="trigger" /></div>' },
  NDivider: { template: '<hr class="n-divider" />' },
  NText: { template: '<span><slot /></span>', props: ['depth', 'type'] },
  NDynamicTags: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NUpload: { template: '<div><slot /></div>', props: ['multiple', 'showFileList', 'fileList', 'customRequest'] },
  NColorPicker: { template: '<input type="color" />', props: ['value'], emits: ['update:value'] },
  NInputNumber: { template: '<input type="number" />', props: ['value', 'min', 'max'], emits: ['update:value'] },
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
  NAutoComplete: {
    name: 'NAutoComplete',
    template: '<div class="n-auto-complete"><input class="ac-input" :value="value" @input="$emit(\'update:value\', $event.target.value)" /></div>',
    props: ['value', 'options', 'loading', 'placeholder', 'clearable', 'size'],
    emits: ['update:value', 'select'],
  },
  useMessage: () => message,
  useDialog: () => ({ warning: vi.fn(), error: vi.fn(), success: vi.fn() }),
  useLoadingBar: () => ({ start: vi.fn(), finish: vi.fn(), error: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/photos', name: 'photos' })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false }, isFetching: { value: false }, error: { value: null }, refetch: vi.fn() })),
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: { value: false }, isError: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn(), setQueryData: vi.fn() })),
  useInfiniteQuery: vi.fn(() => ({ data: { value: { pages: [] } }, isLoading: { value: false }, fetchNextPage: vi.fn(), hasNextPage: { value: false } })),
  keepPreviousData: undefined,
}))

vi.mock('@/api', () => ({ api: vi.fn().mockResolvedValue({ data: {} }), apiUpload: vi.fn().mockResolvedValue({ data: {} }), BASE_URL: '/api/v1' }))
vi.mock('@/api/photos', () => ({
  fetchPermissions: (...args: unknown[]) => fetchPermissionsMock(...args),
  grantPermission: (...args: unknown[]) => grantPermissionMock(...args),
  revokePermission: (...args: unknown[]) => revokePermissionMock(...args),
  searchSubjects: (...args: unknown[]) => searchSubjectsMock(...args),
}))
vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))
vi.mock('@vicons/fluent', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

import PhotoPermissionsModal from '@/components/photos/PhotoPermissionsModal.vue'

const globalPlugins = {
  plugins: [i18n],
  stubs: { RouterLink: { template: '<a><slot /></a>' },
  },
}

const target = { id: 'f-1', name: 'Folder', path: '/Folder', parent_id: null, permission: 'manager', children: [] }

describe('cov2 PhotoPermissionsModal', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    fetchPermissionsMock.mockReset()
    grantPermissionMock.mockReset()
    revokePermissionMock.mockReset()
    searchSubjectsMock.mockReset()
    message.success.mockReset()
    message.error.mockReset()
    message.warning.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads permissions when opened and target exists', async () => {
    fetchPermissionsMock.mockResolvedValue({ items: [{ id: 'p1', subject_id: 'u1', subject_name: 'Alice', subject_type: 'user', permission: 'viewer' }] })

    const wrapper = mount(PhotoPermissionsModal, {
      props: { show: false, target },
      global: globalPlugins,
    })

    await wrapper.setProps({ show: true })
    await flushPromises()
    expect(wrapper.exists()).toBe(true)
    expect(fetchPermissionsMock).toHaveBeenCalledWith('f-1')
    expect(wrapper.find('.n-data-table').exists()).toBe(true)
  })

  it('handles permissions load error branch', async () => {
    fetchPermissionsMock.mockRejectedValue(new Error('fail'))

    const wrapper = mount(PhotoPermissionsModal, {
      props: { show: false, target },
      global: globalPlugins,
    })

    await wrapper.setProps({ show: true })
    await flushPromises()
    expect(wrapper.exists()).toBe(true)
    expect(fetchPermissionsMock).toHaveBeenCalled()
  })

  it('validates empty grant form and shows warning', async () => {
    fetchPermissionsMock.mockResolvedValue({ items: [] })
    searchSubjectsMock.mockResolvedValue([{ subject_id: 'u1', subject_name: '', subject_type: 'user', email: null }])

    const wrapper = mount(PhotoPermissionsModal, {
      props: { show: false, target },
      global: globalPlugins,
    })

    await wrapper.setProps({ show: true })
    await flushPromises()

    const ac = wrapper.findComponent({ name: 'NAutoComplete' })
    ac.vm.$emit('update:value', 'Al')
    await vi.advanceTimersByTimeAsync(450)
    await flushPromises()
    ac.vm.$emit('select', 'u1')
    await flushPromises()

    const addBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('photos.permissions.add'))
    expect(addBtn?.exists()).toBe(true)
    await addBtn!.trigger('click')

    expect(message.warning).toHaveBeenCalled()
    expect(grantPermissionMock).not.toHaveBeenCalled()
  })

  it('searches subjects after debounce and adds permission successfully', async () => {
    fetchPermissionsMock.mockResolvedValue({ items: [] })
    searchSubjectsMock.mockResolvedValue([{ subject_id: 'u1', subject_name: 'Alice', subject_type: 'user', email: 'a@b.c' }])
    grantPermissionMock.mockResolvedValue({ id: 'p-new', subject_id: 'u1', subject_name: 'Alice', subject_type: 'user', permission: 'viewer' })

    const wrapper = mount(PhotoPermissionsModal, {
      props: { show: true, target },
      global: globalPlugins,
    })

    await flushPromises()

    const ac = wrapper.findComponent({ name: 'NAutoComplete' })
    ac.vm.$emit('update:value', 'Al')
    await vi.advanceTimersByTimeAsync(450)
    await flushPromises()

    expect(searchSubjectsMock).toHaveBeenCalledWith('Al')

    ac.vm.$emit('select', 'u1')
    await flushPromises()

    const addBtn = wrapper.findAll('.n-button').at(-1)
    await addBtn!.trigger('click')
    await flushPromises()

    expect(grantPermissionMock).toHaveBeenCalledWith('f-1', expect.objectContaining({ subject_id: 'u1', subject_name: 'Alice' }))
    expect(wrapper.emitted('changed')).toBeTruthy()
    expect(message.success).toHaveBeenCalled()
  })

  it('handles add permission failure branch', async () => {
    fetchPermissionsMock.mockResolvedValue({ items: [] })
    searchSubjectsMock.mockResolvedValue([{ subject_id: 'u1', subject_name: 'Alice', subject_type: 'user', email: null }])
    grantPermissionMock.mockRejectedValue(new Error('grant fail'))

    const wrapper = mount(PhotoPermissionsModal, {
      props: { show: true, target },
      global: globalPlugins,
    })

    await flushPromises()
    const ac = wrapper.findComponent({ name: 'NAutoComplete' })
    ac.vm.$emit('update:value', 'Al')
    await vi.advanceTimersByTimeAsync(450)
    ac.vm.$emit('select', 'u1')
    await flushPromises()

    const addBtn = wrapper.findAll('.n-button').at(-1)
    await addBtn!.trigger('click')
    await flushPromises()

    expect(message.error).toHaveBeenCalled()
  })
})
