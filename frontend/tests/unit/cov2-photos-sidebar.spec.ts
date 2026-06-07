import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const pushMock = vi.fn()
const authStore = { isAdmin: true, isEditor: true }

vi.mock('naive-ui', () => ({
  NButton: { template: '<button @click="$emit(\'click\')"><slot /><slot name="icon" /></button>', props: ['type', 'size', 'disabled', 'loading', 'ghost', 'quaternary', 'tertiary', 'circle', 'title', 'block'], emits: ['click'] },
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
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
  useDialog: () => ({ warning: vi.fn(), error: vi.fn(), success: vi.fn() }),
  useLoadingBar: () => ({ start: vi.fn(), finish: vi.fn(), error: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: pushMock, replace: vi.fn(), back: vi.fn() })),
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
vi.mock('@/stores/auth', () => ({ useAuthStore: vi.fn(() => authStore) }))
vi.mock('@vicons/ionicons5', () => ({ SettingsOutline: { template: '<span />' } }))
vi.mock('@vicons/fluent', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

import PhotosSidebar from '@/components/photos/PhotosSidebar.vue'

const FolderNodeStub = {
  template: '<li class="folder-node-stub" @click="$emit(\'select\', node)"><button class="emit-child" @click.stop="$emit(\'subfolder\', node)">child</button></li>',
  props: ['node', 'selectedId'],
  emits: ['select', 'subfolder', 'permissions', 'delete', 'drag-start', 'drop', 'move-to-root'],
}

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
    SkeletonCard: { template: '<div class="skeleton-card" />' },
    FolderNode: FolderNodeStub,
  },
}

const makeNode = (id: string) => ({ id, name: `Folder ${id}`, path: `/${id}`, parent_id: null, permission: 'manager', children: [] })
const makeTag = (id: string, name: string) => ({ id, name, count: 1 })

describe('cov2 PhotosSidebar', () => {
  beforeEach(() => {
    pushMock.mockReset()
    authStore.isAdmin = true
    authStore.isEditor = true
  })

  it('renders loading branch and admin/editor actions', async () => {
    const wrapper = mount(PhotosSidebar, {
      props: { tree: [], loadingTree: true, selectedFolderId: null, tags: [], activeTagFilter: null },
      global: globalPlugins,
    })

    expect(wrapper.exists()).toBe(true)
    expect(wrapper.findAll('.skeleton-card').length).toBe(6)

    const buttons = wrapper.findAll('button')
    await buttons[0].trigger('click')
    await buttons[1].trigger('click')
    expect(wrapper.emitted('open-module-settings')).toBeTruthy()
    expect(wrapper.emitted('create-root')).toBeTruthy()
  })

  it('renders tree branch and forwards folder events', async () => {
    const wrapper = mount(PhotosSidebar, {
      props: { tree: [makeNode('a1')], loadingTree: false, selectedFolderId: 'a1', tags: [], activeTagFilter: null },
      global: globalPlugins,
    })

    expect(wrapper.find('.folder-tree').exists()).toBe(true)
    expect(wrapper.find('.folder-node-stub').exists()).toBe(true)

    await wrapper.find('.folder-node-stub').trigger('click')
    expect(wrapper.emitted('select')).toBeTruthy()

    await wrapper.find('.emit-child').trigger('click')
    expect(wrapper.emitted('create-child')).toBeTruthy()
  })

  it('renders empty branch when no folders', () => {
    const wrapper = mount(PhotosSidebar, {
      props: { tree: [], loadingTree: false, selectedFolderId: null, tags: [], activeTagFilter: null },
      global: globalPlugins,
    })

    expect(wrapper.find('.photos-side__empty').exists()).toBe(true)
  })

  it('renders tags branch and emits filter events', async () => {
    const tags = [makeTag('t1', 'summer'), makeTag('t2', 'winter')]
    const wrapper = mount(PhotosSidebar, {
      props: { tree: [], loadingTree: false, selectedFolderId: null, tags, activeTagFilter: 't1' },
      global: globalPlugins,
    })

    expect(wrapper.find('.photos-side__tags').exists()).toBe(true)
    expect(wrapper.findAll('.tag-chip').length).toBe(2)

    await wrapper.find('.tag-chip').trigger('click')
    expect(wrapper.emitted('set-tag-filter')).toBeTruthy()

    await wrapper.find('.photos-side__tags-clear').trigger('click')
    expect(wrapper.emitted('clear-tag-filter')).toBeTruthy()
  })

  it('emits import/open-trash and navigates to my shares', async () => {
    const wrapper = mount(PhotosSidebar, {
      props: { tree: [], loadingTree: false, selectedFolderId: null, tags: [], activeTagFilter: null },
      global: globalPlugins,
    })

    const allBtns = wrapper.findAll('button')
    const importBtn = allBtns.find((b) => b.text().includes('photos.import.button'))
    const sharesBtn = allBtns.find((b) => b.text().includes('photos.myShares.title'))
    const trashBtn = allBtns.find((b) => b.text().includes('photos.trash.button'))

    expect(importBtn).toBeDefined()
    expect(sharesBtn).toBeDefined()
    expect(trashBtn).toBeDefined()

    await importBtn!.trigger('click')
    await sharesBtn!.trigger('click')
    await trashBtn!.trigger('click')

    expect(wrapper.emitted('import-scan')).toBeTruthy()
    expect(wrapper.emitted('open-trash')).toBeTruthy()
    expect(pushMock).toHaveBeenCalledWith('/photos/my-shares')
  })

  it('hides admin/editor gated actions when auth flags are false', () => {
    authStore.isAdmin = false
    authStore.isEditor = false

    const wrapper = mount(PhotosSidebar, {
      props: { tree: [], loadingTree: false, selectedFolderId: null, tags: [], activeTagFilter: null },
      global: globalPlugins,
    })

    expect(wrapper.text()).not.toContain('photos.folders.newRoot')
    expect(wrapper.text()).not.toContain('photos.trash.button')
    expect(wrapper.text()).not.toContain('photos.import.button')
  })
})
