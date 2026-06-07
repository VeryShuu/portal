import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const routeState = { query: {} as Record<string, string> }
const getPhotoMock = vi.fn()

const authStore = { isAdmin: true, isEditor: true, user: { id: 'u1' } }

const loadTreeMock = vi.fn().mockResolvedValue(undefined)
const selectFolderMock = vi.fn().mockResolvedValue(undefined)
const loadTagsMock = vi.fn()
const loadPhotosMock = vi.fn()
const togglePhotoSelectMock = vi.fn()
const stopZipPollingMock = vi.fn()

const treeRef = ref<any[]>([])
const selectedFolderRef = ref<any | null>(null)
const selectedFolderIdRef = ref<string | null>(null)
const photosRef = ref<any[]>([])
const lightboxModelRef = ref<number | null>(null)

vi.mock('naive-ui', () => ({
  NButton: { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'disabled', 'loading', 'ghost', 'quaternary', 'tertiary', 'circle', 'title', 'block'], emits: ['click'] },
  NButtonGroup: { template: '<div><slot /></div>' },
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NEmpty: { template: '<div class="n-empty"><slot /></div>', props: ['description'] },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'title', 'showIcon', 'closable'] },
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'size'], emits: ['update:value'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color', 'component'] },
  NCard: { template: '<div class="n-card"><slot /></div>', props: ['bordered', 'size', 'title'] },
  NInput: { template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />', props: ['value', 'placeholder', 'type', 'maxlength', 'size', 'clearable', 'rows'], emits: ['update:value'] },
  NSelect: { template: '<select />', props: ['value', 'options', 'placeholder', 'multiple', 'clearable', 'filterable'], emits: ['update:value'] },
  NPagination: { template: '<div class="n-pagination" />', props: ['page', 'pageCount', 'pageSize'], emits: ['update:page'] },
  NRadioGroup: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NRadioButton: { template: '<label><slot /></label>', props: ['value', 'label'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset', 'positiveText', 'negativeText'], emits: ['update:show', 'positive-click', 'negative-click'] },
  NDrawer: { template: '<div class="n-drawer" v-if="show"><slot /></div>', props: ['show', 'width', 'placement', 'onUpdateShow'], emits: ['update:show'] },
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
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: routeState.query, path: '/photos', name: 'photos-index' })),
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
vi.mock('@/api/photos', () => ({ getPhoto: (...args: unknown[]) => getPhotoMock(...args) }))

vi.mock('@/composables/useManageDrawer', () => ({
  useManageDrawer: () => ({ open: vi.fn(), close: vi.fn(), is: vi.fn(() => false) }),
}))

vi.mock('@/composables/usePhotoFolderSelection', () => ({
  usePhotoFolderSelection: () => ({
    tree: treeRef,
    loadingTree: ref(false),
    selectedFolderId: selectedFolderIdRef,
    selectedFolder: selectedFolderRef,
    editingDescription: ref(false),
    editDescValue: ref(''),
    loadTree: loadTreeMock,
    selectFolder: selectFolderMock,
    startEditDescription: vi.fn(),
    saveDescription: vi.fn(),
    flatten: (nodes: any[]) => nodes.flatMap((n) => [n, ...(n.children || [])]),
    refreshSelectedFolder: vi.fn(),
  }),
}))

vi.mock('@/composables/usePhotoListing', () => ({
  usePhotoListing: () => ({
    photos: photosRef,
    totalPhotos: ref(photosRef.value.length),
    loadingPhotos: ref(false),
    sortBy: ref('new'),
    tags: ref([]),
    photoTagsMap: ref({}),
    activeTagFilter: ref<string | null>(null),
    loadPhotos: loadPhotosMock,
    loadMorePhotos: vi.fn(),
    onSortChange: vi.fn(),
    reloadFromFirstPage: vi.fn(),
    confirmDeletePhoto: vi.fn(),
    loadTags: loadTagsMock,
    setTagFilter: vi.fn(),
    clearTagFilter: vi.fn(),
    onTagsUpdated: vi.fn(),
    resetForFolder: vi.fn(),
  }),
}))

vi.mock('@/composables/usePhotoFolderActions', () => ({
  usePhotoFolderActions: () => ({
    folderModalOpen: ref(false),
    newFolderName: ref(''),
    newFolderDesc: ref(''),
    permsModalOpen: ref(false),
    permsTarget: ref(null),
    openCreateRoot: vi.fn(),
    openCreateChild: vi.fn(),
    submitCreateFolder: vi.fn(),
    confirmDeleteFolder: vi.fn(),
    openPermissions: vi.fn(),
    onFolderDragStart: vi.fn(),
    onFolderDrop: vi.fn(),
    onFolderMoveToRoot: vi.fn(),
  }),
}))

const selectModeRef = ref(false)
vi.mock('@/composables/usePhotoSelection', () => ({
  usePhotoSelection: () => ({
    selectMode: selectModeRef,
    selectedPhotoIds: ref(new Set<string>()),
    moveModalOpen: ref(false),
    moveTargetFolderId: ref<string | null>(null),
    toggleSelectMode: vi.fn(),
    togglePhotoSelect: togglePhotoSelectMock,
    bulkDelete: vi.fn(),
    openMoveModal: vi.fn(),
    confirmMove: vi.fn(),
  }),
}))

vi.mock('@/composables/usePhotoUpload', () => ({
  usePhotoUpload: () => ({
    fileInputRef: ref<HTMLInputElement | null>(null),
    uploadQueue: ref([]),
    uploadAborted: ref(false),
    uploadingActive: ref(false),
    uploadDoneCount: ref(0),
    totalProgress: ref(0),
    isDraggingOver: ref(false),
    triggerUpload: vi.fn(),
    abortUpload: vi.fn(),
    onFilesPicked: vi.fn(),
    onDrop: vi.fn(),
    previewUrls: ref({}),
  }),
}))

vi.mock('@/composables/useZipExport', () => ({
  useZipExport: () => ({
    zipJob: ref(null),
    startZip: vi.fn(),
    stopZipPolling: stopZipPollingMock,
  }),
}))

vi.mock('@/composables/useImportScan', () => ({
  useImportScan: () => ({ confirmImportScan: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))
vi.mock('@vicons/fluent', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

import PhotosIndexPage from '@/pages/photos/PhotosIndexPage.vue'

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
    EmptyState: { template: '<div class="empty-state" />' },
    PhotosSidebar: { template: '<div class="photos-sidebar-stub" />' },
    PhotosFolderHeader: { template: '<div class="folder-header-stub" />' },
    PhotosUploadQueue: { template: '<div class="upload-queue-stub" />' },
    PhotosGrid: {
      template: '<div class="photos-grid-stub"><button class="emit-photo-click" @click="$emit(\'photo-click\', { id: \'p-grid\', uploaded_by: \'u1\' }, 2)">click</button></div>',
      emits: ['photo-click', 'toggle-select', 'delete-photo', 'load-more', 'bulk-delete', 'open-move', 'toggle-select-mode', 'drag-over', 'drag-leave', 'drop'],
    },
    LightboxModal: { template: '<div class="lightbox-modal-stub" :data-model="modelValue" />', props: ['modelValue'] },
    PhotoPermissionsModal: { template: '<div class="photo-perms-stub" />' },
    PhotoTrashView: { template: '<div class="photo-trash-stub" />' },
    PhotosModuleSettings: { template: '<div class="photo-module-settings-stub" />' },
    Suspense: { template: '<div><slot /></div>' },
  },
}

describe('cov2 PhotosIndexPage', () => {
  beforeEach(() => {
    routeState.query = {}
    getPhotoMock.mockReset()
    loadTreeMock.mockClear()
    selectFolderMock.mockClear()
    loadTagsMock.mockClear()
    loadPhotosMock.mockClear()
    togglePhotoSelectMock.mockClear()
    stopZipPollingMock.mockClear()

    treeRef.value = []
    selectedFolderRef.value = { id: 'f1', permission: 'manager' }
    selectedFolderIdRef.value = 'f1'
    photosRef.value = []
    selectModeRef.value = false
  })

  it('mounts and runs default onMounted flow', async () => {
    const wrapper = mount(PhotosIndexPage, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    expect(loadTreeMock).toHaveBeenCalled()
    expect(loadTagsMock).toHaveBeenCalled()
    expect(loadPhotosMock).not.toHaveBeenCalled()
  })

  it('selects folder from route query when found in flattened tree', async () => {
    treeRef.value = [{ id: 'root-a', name: 'A', children: [{ id: 'folder-2', name: 'B', children: [] }] }]
    routeState.query = { folder: 'folder-2' }

    mount(PhotosIndexPage, { global: globalPlugins })
    await flushPromises()

    expect(selectFolderMock).toHaveBeenCalledWith(expect.objectContaining({ id: 'folder-2' }))
  })

  it('opens lightbox with existing photo from route query', async () => {
    photosRef.value = [{ id: 'p-existing', uploaded_by: 'u1' }]
    routeState.query = { photo: 'p-existing' }

    const wrapper = mount(PhotosIndexPage, { global: globalPlugins })
    await flushPromises()

    const lightbox = wrapper.find('.lightbox-modal-stub')
    expect(lightbox.attributes('data-model')).toBe('0')
  })

  it('fetches photo when route photo is missing and prepends it', async () => {
    photosRef.value = [{ id: 'p1', uploaded_by: 'u2' }]
    routeState.query = { photo: 'p-missing' }
    getPhotoMock.mockResolvedValue({ id: 'p-missing', uploaded_by: 'u3' })

    const wrapper = mount(PhotosIndexPage, { global: globalPlugins })
    await flushPromises()

    expect(getPhotoMock).toHaveBeenCalledWith('p-missing')
    expect(photosRef.value[0].id).toBe('p-missing')
    expect(wrapper.find('.lightbox-modal-stub').attributes('data-model')).toBe('0')
  })

  it('handles getPhoto failure branch gracefully', async () => {
    routeState.query = { photo: 'p-fail' }
    getPhotoMock.mockRejectedValue(new Error('404'))

    const wrapper = mount(PhotosIndexPage, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    expect(getPhotoMock).toHaveBeenCalledWith('p-fail')
  })

  it('onPhotoClick toggles selection in select mode and opens lightbox otherwise', async () => {
    photosRef.value = [{ id: 'p-grid', uploaded_by: 'u1' }]

    const wrapper = mount(PhotosIndexPage, { global: globalPlugins })
    await flushPromises()

    selectModeRef.value = true
    await wrapper.find('.emit-photo-click').trigger('click')
    expect(togglePhotoSelectMock).toHaveBeenCalledWith('p-grid')

    selectModeRef.value = false
    await wrapper.find('.emit-photo-click').trigger('click')
    expect(wrapper.find('.lightbox-modal-stub').attributes('data-model')).toBe('2')
  })
})
