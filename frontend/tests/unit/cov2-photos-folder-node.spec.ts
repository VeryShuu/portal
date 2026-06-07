import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'disabled', 'loading', 'ghost', 'quaternary', 'tertiary', 'circle', 'title'], emits: ['click'] },
  NButtonGroup: { template: '<div><slot /></div>' },
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NEmpty: { template: '<div class="n-empty"><slot /></div>', props: ['description'] },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'title', 'showIcon', 'closable'] },
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'size'], emits: ['update:value'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color', 'component'] },
  NCard: { template: '<div class="n-card"><slot /></div>', props: ['bordered', 'size', 'title'] },
  NInput: { template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />', props: ['value', 'placeholder', 'type', 'maxlength', 'size', 'clearable'], emits: ['update:value'] },
  NSelect: { template: '<select />', props: ['value', 'options', 'placeholder', 'multiple', 'clearable'], emits: ['update:value'] },
  NPagination: { template: '<div class="n-pagination" />', props: ['page', 'pageCount', 'pageSize'], emits: ['update:page'] },
  NRadioGroup: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NRadioButton: { template: '<label><slot /></label>', props: ['value', 'label'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset'], emits: ['update:show'] },
  NDrawer: { template: '<div class="n-drawer" v-if="show"><slot /></div>', props: ['show', 'width', 'placement'], emits: ['update:show'] },
  NDrawerContent: { template: '<div><slot /></div>', props: ['title', 'closable'] },
  NForm: { template: '<form><slot /></form>', props: ['model', 'rules'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path'] },
  NCheckbox: { template: '<input type="checkbox" />', props: ['checked'], emits: ['update:checked'] },
  NSwitch: { template: '<input type="checkbox" />', props: ['value'], emits: ['update:value'] },
  NDataTable: { template: '<div class="n-data-table" />', props: ['data', 'columns', 'pagination', 'loading'] },
  NSpace: { template: '<div><slot /></div>', props: ['justify', 'align', 'size', 'vertical'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'closable', 'bordered'] },
  NTooltip: { template: '<div><slot /><slot name="trigger" /></div>' },
  NPopconfirm: { template: '<div><slot /><slot name="trigger" /></div>' },
  NDivider: { template: '<hr />' },
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
  NDropdown: { name: 'NDropdown', template: '<div class="n-dropdown"><slot /></div>', props: ['options', 'trigger'], emits: ['select'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
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
vi.mock('@/api/photos', () => ({ thumbUrl: vi.fn((id: string, size: number) => `/thumb/${id}/${size}`) }))
vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))
vi.mock('@vicons/fluent', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

import FolderNode from '@/components/photos/FolderNode.vue'

const globalPlugins = {
  plugins: [i18n],
  stubs: { RouterLink: { template: '<a><slot /></a>' } },
}

const makeNode = (overrides: Record<string, unknown> = {}) => ({
  id: 'root-1',
  name: 'Root',
  path: '/Root',
  parent_id: null,
  permission: 'manager',
  cover_photo_id: null,
  children: [],
  ...overrides,
})

describe('cov2 FolderNode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders leaf node branch and emits select', async () => {
    const wrapper = mount(FolderNode, {
      props: { node: makeNode({ permission: 'viewer' }), selectedId: null },
      global: globalPlugins,
    })

    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.folder-node__toggle--leaf').exists()).toBe(true)
    expect(wrapper.find('.folder-node__menu').exists()).toBe(false)

    await wrapper.find('.folder-node__name').trigger('click')
    expect(wrapper.emitted('select')).toBeTruthy()
  })

  it('renders folder with children, toggles open, and has draggable row for manager', async () => {
    const child = makeNode({ id: 'child-1', name: 'Child', path: '/Root/Child', parent_id: 'root-1', children: [] })
    const wrapper = mount(FolderNode, {
      props: { node: makeNode({ children: [child] }), selectedId: 'root-1' },
      global: globalPlugins,
    })

    const row = wrapper.find('.folder-node__row')
    expect(row.classes()).toContain('selected')
    expect(row.attributes('draggable')).toBe('true')
    expect(wrapper.find('.folder-node__children').exists()).toBe(true)

    await wrapper.find('.folder-node__toggle').trigger('click')
    expect(wrapper.find('.folder-node__children').exists()).toBe(false)
  })

  it('handles dragstart/dragover/dragleave/drop branches', async () => {
    const wrapper = mount(FolderNode, {
      props: { node: makeNode(), selectedId: null },
      global: globalPlugins,
    })

    const row = wrapper.find('.folder-node__row')
    const dt = { effectAllowed: 'none' }

    await row.trigger('dragstart', { dataTransfer: dt })
    expect(dt.effectAllowed).toBe('move')
    expect(wrapper.emitted('drag-start')).toBeTruthy()

    await row.trigger('dragover')
    expect(row.classes()).toContain('folder-node__row--drag-over')

    await row.trigger('dragleave')
    expect(row.classes()).not.toContain('folder-node__row--drag-over')

    await row.trigger('drop')
    expect(wrapper.emitted('drop')).toBeTruthy()
  })

  it('emits menu actions including move-to-root and delete', async () => {
    const wrapper = mount(FolderNode, {
      props: { node: makeNode({ parent_id: 'p-1' }), selectedId: null },
      global: globalPlugins,
    })

    const dd = wrapper.findComponent({ name: 'NDropdown' })
    expect(dd.exists()).toBe(true)

    dd.vm.$emit('select', 'subfolder')
    dd.vm.$emit('select', 'permissions')
    dd.vm.$emit('select', 'move-to-root')
    dd.vm.$emit('select', 'delete')

    expect(wrapper.emitted('subfolder')).toBeTruthy()
    expect(wrapper.emitted('permissions')).toBeTruthy()
    expect(wrapper.emitted('move-to-root')).toBeTruthy()
    expect(wrapper.emitted('delete')).toBeTruthy()
  })
})
