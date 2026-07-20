import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { computed, defineComponent, nextTick, reactive, ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  messages: { ru: {}, en: {} },
  missingWarn: false,
  fallbackWarn: false,
  silentFallbackWarn: true,
  silentTranslationWarn: true,
})

const mockRouteState: { query: Record<string, string>; params: Record<string, string> } = {
  query: {},
  params: {},
}

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: vi.fn(() => mockRouteState),
  }
})

const mockMessageSuccess = vi.fn()
const mockMessageError = vi.fn()

vi.mock('naive-ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('naive-ui')>()
  return {
    ...actual,
    NDrawer: {
      template: '<div v-if="show" class="n-drawer"><slot /></div>',
      props: ['show', 'width', 'placement', 'onUpdateShow'],
    },
    NDrawerContent: {
      template: '<div class="n-drawer-content"><slot /></div>',
      props: ['title', 'closable'],
    },
    useMessage: () => ({ success: mockMessageSuccess, error: mockMessageError }),
  }
})

const mockDeleteFile = vi.fn()
const mockPreviewFile = vi.fn((folderId: string, filename: string) => `/preview/${folderId}/${filename}`)
const mockIsPreviewableImage = vi.fn((item: { name?: string }) => Boolean(item?.name?.toLowerCase().endsWith('.png')))
const mockIsPreviewablePdf = vi.fn((item: { name?: string }) => Boolean(item?.name?.toLowerCase().endsWith('.pdf')))

vi.mock('../../src/api/files', () => ({
  BULK_DOWNLOAD_LIMIT: 20,
  deleteFile: (...args: unknown[]) => mockDeleteFile(...args),
  previewFile: (...args: unknown[]) => mockPreviewFile(...args),
  isPreviewableImage: (...args: unknown[]) => mockIsPreviewableImage(...args),
  isPreviewablePdf: (...args: unknown[]) => mockIsPreviewablePdf(...args),
}))

const mockConfirm = vi.fn()
vi.mock('../../src/composables/useConfirmDialog', () => ({
  useConfirmDialog: vi.fn(() => ({ confirm: (...args: unknown[]) => mockConfirm(...args) })),
}))

const manageState = {
  active: ref<string | null>(null),
  open: vi.fn(),
  close: vi.fn(() => { manageState.active.value = null }),
  is: vi.fn((key: string) => manageState.active.value === key),
}

vi.mock('../../src/composables/useManageDrawer', () => ({
  useManageDrawer: vi.fn(() => manageState),
}))

const mockOpenCollabora = vi.fn()
const collaboraState = {
  openingCollaboraFile: ref<string | null>(null),
  openCollabora: (...args: unknown[]) => mockOpenCollabora(...args),
}

vi.mock('../../src/composables/useCollabora', () => ({
  useCollabora: vi.fn(() => collaboraState),
}))

const selectionState = {
  selectedKeys: ref<string[]>([]),
  selectedFilenames: computed(() => [] as string[]),
  clearSelection: vi.fn(() => {
    selectionState.selectedKeys.value = []
  }),
  onRowClick: vi.fn(),
}

vi.mock('../../src/composables/useFilesSelection', () => ({
  useFilesSelection: vi.fn(() => selectionState),
}))

const uploadState = {
  uploading: ref(false),
  uploadProgress: ref({ done: 0, total: 0, failed: 0 }),
  fileInputRef: ref<HTMLInputElement | null>(null),
  dndActive: ref(false),
  triggerUpload: vi.fn(),
  handleFileInput: vi.fn(),
  onMainDragEnter: vi.fn(),
  onMainDragOver: vi.fn(),
  onMainDragLeave: vi.fn(),
  onMainDrop: vi.fn(),
}

vi.mock('../../src/composables/useFilesUpload', () => ({
  useFilesUpload: vi.fn(() => uploadState),
}))

const bulkState = {
  bulkBusy: ref(false),
  showMoveModal: ref(false),
  moveTreeData: ref([]),
  moveTargetKey: ref<string | null>(null),
  bulkDownload: vi.fn(),
  openMoveModal: vi.fn(),
  confirmBulkDelete: vi.fn(),
  submitBulkMove: vi.fn(),
}

vi.mock('../../src/composables/useFilesBulkOps', () => ({
  useFilesBulkOps: vi.fn(() => bulkState),
}))

const authState = reactive({ isAdmin: false, isEditor: false })
vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => authState),
}))

let storeState: {
  tree: unknown[]
  loadingTree: boolean
  selectedFolderId: string | null
  currentFolder: { id: string; parent_id: string | null; inherit_permissions: boolean } | null
  ncItems: Array<{ name: string; nc_path: string; is_dir?: boolean; mime_type?: string | null }>
  breadcrumbs: unknown[]
  loadingDetail: boolean
  syncing: boolean
  canUpload: boolean
  canManage: boolean
  canEdit: boolean
  findNodeById: ReturnType<typeof vi.fn>
  findNodeByNcPath: ReturnType<typeof vi.fn>
  selectFolder: ReturnType<typeof vi.fn>
  loadTree: ReturnType<typeof vi.fn>
  loadDetail: ReturnType<typeof vi.fn>
  createFolder: ReturnType<typeof vi.fn>
  deleteFolder: ReturnType<typeof vi.fn>
  syncFromNextcloud: ReturnType<typeof vi.fn>
  refreshCurrent: ReturnType<typeof vi.fn>
}

vi.mock('../../src/composables/useFilesData', () => ({
  useFilesData: vi.fn(() => storeState),
}))

vi.mock('../../src/pages/admin/tabs/FileIconsTab.vue', () => ({
  __esModule: true,
  __isTeleport: false,
  __isKeepAlive: false,
  default: defineComponent({ template: '<div class="file-icons-tab" />' }),
}))
vi.mock('../../src/pages/admin/tabs/FileSharesTab.vue', () => ({
  __esModule: true,
  __isTeleport: false,
  __isKeepAlive: false,
  default: defineComponent({ template: '<div class="file-shares-tab" />' }),
}))

const FilesSidebarStub = defineComponent({
  name: 'FilesSidebar',
  props: {
    tree: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
    selectedId: { type: String, default: null },
    isAdmin: { type: Boolean, default: false },
    isEditor: { type: Boolean, default: false },
    syncing: { type: Boolean, default: false },
    activeView: { type: String, default: 'folders' },
  },
  emits: ['select', 'create-root', 'create-child', 'manage', 'delete', 'sync', 'manage-icons', 'manage-shares', 'open-my-shares', 'open-shared-with-me'],
  template: '<div class="files-sidebar" />',
})

const EmptyStateStub = defineComponent({
  name: 'EmptyState',
  props: { variant: { type: String, default: '' }, title: { type: String, default: '' }, description: { type: String, default: '' } },
  template: '<div class="empty-state" />',
})

const FilesDropZoneStub = defineComponent({
  name: 'FilesDropZone',
  props: { active: { type: Boolean, default: false } },
  template: '<div class="files-drop-zone" />',
})

const FilesSharesPanelStub = defineComponent({
  name: 'FilesSharesPanel',
  props: { mode: { type: String, default: 'my' } },
  template: '<div class="files-shares-panel" />',
})

const FilesBreadcrumbsStub = defineComponent({
  name: 'FilesBreadcrumbs',
  props: { breadcrumbs: { type: Array, default: () => [] }, current: { type: Object, default: null } },
  emits: ['select'],
  setup(_props, { emit }) {
    const onClick = () => emit('select', 'crumb-1')
    return { onClick }
  },
  template: '<div class="files-breadcrumbs" @click="onClick" />',
})

const FilesToolbarStub = defineComponent({
  name: 'FilesToolbar',
  props: {
    currentFolder: { type: Object, default: null },
    canUpload: { type: Boolean, default: false },
    canManage: { type: Boolean, default: false },
    canEdit: { type: Boolean, default: false },
    uploading: { type: Boolean, default: false },
    uploadProgress: { type: Object, default: () => ({}) },
  },
  emits: ['upload-click', 'manage-click'],
  template: '<div class="files-toolbar"><button class="toolbar-upload" @click="$emit(\'upload-click\')" /><button class="toolbar-manage" @click="$emit(\'manage-click\')" /></div>',
})

const FilesBulkBarStub = defineComponent({
  name: 'FilesBulkBar',
  props: { count: { type: Number, default: 0 }, canUpload: { type: Boolean, default: false }, bulkBusy: { type: Boolean, default: false }, downloadLimit: { type: Number, default: 20 } },
  emits: ['download', 'move', 'delete', 'clear'],
  template: '<div class="files-bulk-bar"><button class="bulk-download" @click="$emit(\'download\')" /><button class="bulk-move" @click="$emit(\'move\')" /><button class="bulk-delete" @click="$emit(\'delete\')" /><button class="bulk-clear" @click="$emit(\'clear\')" /></div>',
})

const FilesTableStub = defineComponent({
  name: 'FilesTable',
  props: {
    items: { type: Array, default: () => [] },
    loading: { type: Boolean, default: false },
    selectedKeys: { type: Array, default: () => [] },
    canUpload: { type: Boolean, default: false },
    canEdit: { type: Boolean, default: false },
    canManage: { type: Boolean, default: false },
    folderId: { type: String, default: null },
    openingCollaboraFile: { type: String, default: null },
  },
  emits: ['update:selected-keys', 'row-click', 'preview-image', 'preview-pdf', 'open-collabora', 'delete-file', 'share-file'],
  setup(_props, { emit }) {
    const emitRowClick = () => emit('row-click', {
      row: { name: 'n.png', nc_path: '/p/n.png', is_dir: false },
      index: 3,
      event: { shiftKey: false, ctrlKey: false, metaKey: false },
    })
    const emitPreviewImage = () => emit('preview-image', { name: 'a.png', nc_path: '/x/a.png', is_dir: false })
    const emitPreviewPdf = () => emit('preview-pdf', { name: 'a.pdf', nc_path: '/x/a.pdf', is_dir: false })
    const emitOpenCollabora = () => emit('open-collabora', { name: 'a.docx', nc_path: '/x/a.docx', is_dir: false })
    const emitDeleteFile = () => emit('delete-file', { name: 'a.txt', nc_path: '/x/a.txt', is_dir: false })
    const emitShareFile = () => emit('share-file', { name: 'a.txt', nc_path: '/x/a.txt', is_dir: false })
    return { emitRowClick, emitPreviewImage, emitPreviewPdf, emitOpenCollabora, emitDeleteFile, emitShareFile }
  },
  template: '<div class="files-table"><button class="row-click" @click="emitRowClick" /><button class="preview-image" @click="emitPreviewImage" /><button class="preview-pdf" @click="emitPreviewPdf" /><button class="open-collabora" @click="emitOpenCollabora" /><button class="delete-file" @click="emitDeleteFile" /><button class="share-file" @click="emitShareFile" /></div>',
})

const FilesCreateFolderModalStub = defineComponent({
  name: 'FilesCreateFolderModal',
  props: { show: { type: Boolean, default: false }, loading: { type: Boolean, default: false } },
  emits: ['update:show', 'submit'],
  setup(_props, { emit }) {
    const emitSubmit = () => emit('submit', { name: 'Folder A', description: 'Desc' })
    return { emitSubmit }
  },
  template: '<div v-if="show" class="files-create-modal"><button class="create-submit" @click="emitSubmit" /></div>',
})

const FilesMoveModalStub = defineComponent({
  name: 'FilesMoveModal',
  props: { show: { type: Boolean, default: false }, treeData: { type: Array, default: () => [] }, targetKey: { type: String, default: null }, loading: { type: Boolean, default: false } },
  emits: ['update:show', 'update:target-key', 'confirm'],
  template: '<div v-if="show" class="files-move-modal"><button class="move-confirm" @click="$emit(\'confirm\')" /></div>',
})

const FilesPermissionsModalStub = defineComponent({
  name: 'FilesPermissionsModal',
  props: {
    show: { type: Boolean, default: false },
    folderId: { type: String, default: null },
    parentId: { type: String, default: null },
    inheritPermissions: { type: Boolean, default: true },
  },
  emits: ['update:show', 'tree-refresh'],
  template: '<div v-if="show" class="files-perms-modal" />',
})

const FilesShareModalStub = defineComponent({
  name: 'FilesShareModal',
  props: { show: { type: Boolean, default: false }, folderId: { type: String, default: null }, filename: { type: String, default: null } },
  emits: ['update:show'],
  template: '<div v-if="show" class="files-share-modal" />',
})

const FilesImagePreviewStub = defineComponent({
  name: 'FilesImagePreview',
  props: { images: { type: Array, default: () => [] }, initialIndex: { type: Number, default: 0 }, folderId: { type: String, default: null } },
  emits: ['close'],
  template: '<div class="files-image-preview" />',
})

const SkeletonCardStub = defineComponent({
  name: 'SkeletonCard',
  props: { variant: { type: String, default: 'file-row' } },
  template: '<div class="skeleton-card" />',
})

const globalOptions = {
  plugins: [i18n],
  stubs: {
    FilesSidebar: FilesSidebarStub,
    EmptyState: EmptyStateStub,
    FilesDropZone: FilesDropZoneStub,
    FilesSharesPanel: FilesSharesPanelStub,
    FilesBreadcrumbs: FilesBreadcrumbsStub,
    FilesToolbar: FilesToolbarStub,
    FilesBulkBar: FilesBulkBarStub,
    FilesTable: FilesTableStub,
    FilesCreateFolderModal: FilesCreateFolderModalStub,
    FilesMoveModal: FilesMoveModalStub,
    FilesPermissionsModal: FilesPermissionsModalStub,
    FilesShareModal: FilesShareModalStub,
    FilesImagePreview: FilesImagePreviewStub,
    SkeletonCard: SkeletonCardStub,
  },
}

describe('FilesPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockRouteState.query = {}
    mockRouteState.params = {}
    authState.isAdmin = false
    authState.isEditor = false

    manageState.active.value = null
    manageState.open.mockClear()
    manageState.close.mockClear()
    manageState.is.mockClear()

    selectionState.selectedKeys.value = []
    selectionState.clearSelection.mockClear()
    selectionState.onRowClick.mockClear()

    uploadState.uploading.value = false
    uploadState.uploadProgress.value = { done: 0, total: 0, failed: 0 }
    uploadState.dndActive.value = false
    uploadState.triggerUpload.mockClear()
    uploadState.handleFileInput.mockClear()
    uploadState.onMainDragEnter.mockClear()
    uploadState.onMainDragOver.mockClear()
    uploadState.onMainDragLeave.mockClear()
    uploadState.onMainDrop.mockClear()

    bulkState.bulkBusy.value = false
    bulkState.showMoveModal.value = false
    bulkState.moveTreeData.value = []
    bulkState.moveTargetKey.value = null
    bulkState.bulkDownload.mockClear()
    bulkState.openMoveModal.mockClear()
    bulkState.confirmBulkDelete.mockClear()
    bulkState.submitBulkMove.mockClear()

    collaboraState.openingCollaboraFile.value = null
    mockOpenCollabora.mockClear()

    mockDeleteFile.mockResolvedValue(undefined)
    mockDeleteFile.mockClear()
    mockPreviewFile.mockClear()
    mockIsPreviewableImage.mockClear()
    mockIsPreviewablePdf.mockClear()

    mockConfirm.mockReset()
    mockConfirm.mockResolvedValue(true)

    mockMessageSuccess.mockClear()
    mockMessageError.mockClear()

    storeState = reactive({
      tree: [],
      loadingTree: false,
      selectedFolderId: null,
      currentFolder: null,
      ncItems: [],
      breadcrumbs: [],
      loadingDetail: false,
      syncing: false,
      canUpload: false,
      canManage: false,
      canEdit: false,
      findNodeById: vi.fn(() => null),
      findNodeByNcPath: vi.fn(() => null),
      selectFolder: vi.fn((id: string | null) => {
        storeState.selectedFolderId = id
      }),
      loadTree: vi.fn(async () => {}),
      loadDetail: vi.fn(async () => {}),
      createFolder: vi.fn(async () => {}),
      deleteFolder: vi.fn(async () => {}),
      syncFromNextcloud: vi.fn(async () => ({ created: 0, skipped: 0 })),
      refreshCurrent: vi.fn(async () => {}),
    })

    vi.stubGlobal('open', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses shared-with-me mode from route query on mount and calls loadTree', async () => {
    mockRouteState.query = { tab: 'shared-with-me' }

    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    const sharesPanel = wrapper.findComponent(FilesSharesPanelStub)
    expect(sharesPanel.exists()).toBe(true)
    expect(sharesPanel.props('mode')).toBe('shared-with-me')
    expect(storeState.loadTree).toHaveBeenCalledTimes(1)
  }, 15000)

  it('shows loadTree error message when tree loading fails on mount', async () => {
    storeState.loadTree = vi.fn(async () => {
      throw new Error('tree fail')
    })

    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    mount(FilesPage, { global: globalOptions })
    await flushPromises()

    expect(mockMessageError).toHaveBeenCalled()
  })

  it('watches selectedFolderId and loads detail; on error shows folder error', async () => {
    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    mount(FilesPage, { global: globalOptions })
    await flushPromises()

    storeState.selectedFolderId = 'folder-1'
    await nextTick()
    await flushPromises()

    expect(storeState.loadDetail).toHaveBeenCalledWith('folder-1')

    storeState.loadDetail = vi.fn(async () => {
      throw new Error('detail fail')
    })
    storeState.selectedFolderId = 'folder-2'
    await nextTick()
    await flushPromises()

    expect(mockMessageError).toHaveBeenCalled()
  })

  it('switches from shares view to folders on sidebar select and calls store.selectFolder', async () => {
    mockRouteState.query = { tab: 'my-shares' }

    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    await wrapper.findComponent(FilesSidebarStub).vm.$emit('select', 'folder-99')
    await nextTick()

    expect(storeState.selectFolder).toHaveBeenCalledWith('folder-99')
    expect(wrapper.findComponent(FilesSharesPanelStub).exists()).toBe(false)
  })

  it('handles create root and create child actions; submit passes parent_id and shows success', async () => {
    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    await wrapper.findComponent(FilesSidebarStub).vm.$emit('create-root')
    await nextTick()
    await wrapper.find('.files-create-modal .create-submit').trigger('click')
    await flushPromises()

    expect(storeState.createFolder).toHaveBeenCalledWith({ name: 'Folder A', parent_id: null, description: 'Desc' })

    await wrapper.findComponent(FilesSidebarStub).vm.$emit('create-child', 'parent-7')
    await nextTick()
    await wrapper.find('.files-create-modal .create-submit').trigger('click')
    await flushPromises()

    expect(storeState.createFolder).toHaveBeenLastCalledWith({ name: 'Folder A', parent_id: 'parent-7', description: 'Desc' })
    expect(mockMessageSuccess).toHaveBeenCalled()
  })

  it('shows createFolder error message on create submit failure', async () => {
    storeState.createFolder = vi.fn(async () => {
      throw new Error('create fail')
    })

    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    await wrapper.findComponent(FilesSidebarStub).vm.$emit('create-root')
    await nextTick()
    await wrapper.find('.files-create-modal .create-submit').trigger('click')
    await flushPromises()

    expect(mockMessageError).toHaveBeenCalled()
  })

  it('opens manage modal and passes folder inheritance props from computed node', async () => {
    storeState.findNodeById = vi.fn((id: string) => (id === 'folder-a' ? { id: 'folder-a', parent_id: 'parent-z', inherit_permissions: false } : null))

    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    await wrapper.findComponent(FilesSidebarStub).vm.$emit('manage', 'folder-a')
    await nextTick()

    const perms = wrapper.findComponent(FilesPermissionsModalStub)
    expect(perms.props('show')).toBe(true)
    expect(perms.props('folderId')).toBe('folder-a')
    expect(perms.props('parentId')).toBe('parent-z')
    expect(perms.props('inheritPermissions')).toBe(false)
  })

  it('deletes folder only when confirmed and reports success/error', async () => {
    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    mockConfirm.mockResolvedValueOnce(false)
    await wrapper.findComponent(FilesSidebarStub).vm.$emit('delete', 'folder-del')
    await flushPromises()
    expect(storeState.deleteFolder).not.toHaveBeenCalled()

    mockConfirm.mockResolvedValueOnce(true)
    await wrapper.findComponent(FilesSidebarStub).vm.$emit('delete', 'folder-del')
    await flushPromises()
    expect(storeState.deleteFolder).toHaveBeenCalledWith('folder-del')
    expect(mockMessageSuccess).toHaveBeenCalled()

    storeState.deleteFolder = vi.fn(async () => {
      throw new Error('delete fail')
    })
    mockConfirm.mockResolvedValueOnce(true)
    await wrapper.findComponent(FilesSidebarStub).vm.$emit('delete', 'folder-del-2')
    await flushPromises()
    expect(mockMessageError).toHaveBeenCalled()
  })

  it('sync handler reports success and error states', async () => {
    storeState.syncFromNextcloud = vi.fn(async () => ({ created: 5, skipped: 2 }))

    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    await wrapper.findComponent(FilesSidebarStub).vm.$emit('sync')
    await flushPromises()

    expect(storeState.syncFromNextcloud).toHaveBeenCalledTimes(1)
    expect(mockMessageSuccess).toHaveBeenCalled()

    storeState.syncFromNextcloud = vi.fn(async () => {
      throw new Error('sync fail')
    })
    await wrapper.findComponent(FilesSidebarStub).vm.$emit('sync')
    await flushPromises()

    expect(mockMessageError).toHaveBeenCalled()
  })

  it('routes table events to selection, upload, bulk, collabora and share handlers', async () => {
    storeState.selectedFolderId = 'folder-1'
    storeState.currentFolder = { id: 'folder-1', parent_id: null, inherit_permissions: true }
    storeState.ncItems = [
      { name: 'a.png', nc_path: '/f/a.png', is_dir: false },
      { name: 'b.pdf', nc_path: '/f/b.pdf', is_dir: false },
    ]
    storeState.canUpload = true
    storeState.canManage = true
    storeState.canEdit = true
    selectionState.selectedKeys.value = ['/f/a.png']

    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    await wrapper.find('.toolbar-upload').trigger('click')
    await wrapper.find('.toolbar-manage').trigger('click')
    expect(wrapper.find('.files-bulk-bar').exists()).toBe(true)

    await wrapper.find('.bulk-download').trigger('click')
    await wrapper.find('.bulk-move').trigger('click')
    await wrapper.find('.bulk-delete').trigger('click')
    await wrapper.find('.bulk-clear').trigger('click')
    await wrapper.find('.row-click').trigger('click')
    await wrapper.find('.open-collabora').trigger('click')
    await wrapper.find('.share-file').trigger('click')

    expect(uploadState.triggerUpload).toHaveBeenCalledTimes(1)
    expect(bulkState.bulkDownload).toHaveBeenCalledTimes(1)
    expect(bulkState.openMoveModal).toHaveBeenCalledTimes(1)
    expect(bulkState.confirmBulkDelete).toHaveBeenCalledTimes(1)
    expect(selectionState.clearSelection).toHaveBeenCalledTimes(1)
    expect(selectionState.onRowClick).toHaveBeenCalledTimes(1)
    expect(mockOpenCollabora).toHaveBeenCalledTimes(1)

    const shareModal = wrapper.findComponent(FilesShareModalStub)
    expect(shareModal.props('show')).toBe(true)
    expect(shareModal.props('filename')).toBe('a.txt')
  })

  it('handles delete file flow with confirm/success/error branches', async () => {
    storeState.selectedFolderId = 'folder-2'
    storeState.currentFolder = { id: 'folder-2', parent_id: null, inherit_permissions: true }
    storeState.ncItems = [{ name: 'a.txt', nc_path: '/f/a.txt', is_dir: false }]

    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    mockConfirm.mockResolvedValueOnce(false)
    await wrapper.find('.delete-file').trigger('click')
    await flushPromises()
    expect(mockDeleteFile).not.toHaveBeenCalled()

    mockConfirm.mockResolvedValueOnce(true)
    await wrapper.find('.delete-file').trigger('click')
    await flushPromises()
    expect(mockDeleteFile).toHaveBeenCalledWith('folder-2', 'a.txt')
    expect(storeState.refreshCurrent).toHaveBeenCalled()

    mockDeleteFile.mockRejectedValueOnce(new Error('delete file fail'))
    storeState.selectedFolderId = 'folder-2'
    mockConfirm.mockResolvedValueOnce(true)
    await wrapper.find('.delete-file').trigger('click')
    await flushPromises()
    expect(mockMessageError).toHaveBeenCalled()
  })

  it('opens image preview with computed image list and index; closes on close event', async () => {
    storeState.selectedFolderId = 'folder-3'
    storeState.currentFolder = { id: 'folder-3', parent_id: null, inherit_permissions: true }
    storeState.ncItems = [
      { name: 'x.txt', nc_path: '/f/x.txt', is_dir: false },
      { name: 'a.png', nc_path: '/f/a.png', is_dir: false },
      { name: 'b.png', nc_path: '/f/b.png', is_dir: false },
    ]

    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    await wrapper.find('.preview-image').trigger('click')
    await nextTick()

    const preview = wrapper.findComponent(FilesImagePreviewStub)
    expect(preview.exists()).toBe(true)
    expect((preview.props('images') as Array<{ name: string }>).map(x => x.name)).toEqual(['a.png', 'b.png'])
    expect(preview.props('initialIndex')).toBe(0)

    await preview.vm.$emit('close')
    await nextTick()
    expect(wrapper.findComponent(FilesImagePreviewStub).exists()).toBe(false)
  })

  it('opens PDF preview in new tab only when selectedFolderId exists', async () => {
    storeState.selectedFolderId = 'folder-pdf'
    storeState.currentFolder = { id: 'folder-pdf', parent_id: null, inherit_permissions: true }
    storeState.ncItems = [{ name: 'a.pdf', nc_path: '/f/a.pdf', is_dir: false }]

    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    await wrapper.find('.preview-pdf').trigger('click')
    expect(mockPreviewFile).toHaveBeenCalledWith('folder-pdf', 'a.pdf')
    expect(window.open).toHaveBeenCalledWith('/preview/folder-pdf/a.pdf', '_blank', 'noopener,noreferrer')

    storeState.selectedFolderId = null
    await wrapper.find('.preview-pdf').trigger('click')
    expect(mockPreviewFile).toHaveBeenCalledTimes(1)
  })

  it('renders loading skeleton and empty states branches', async () => {
    storeState.selectedFolderId = null

    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    expect(wrapper.find('.empty-state').exists()).toBe(true)

    storeState.selectedFolderId = 'folder-a'
    storeState.loadingDetail = true
    await nextTick()
    expect(wrapper.findAll('.skeleton-card').length).toBe(8)

    storeState.loadingDetail = false
    storeState.ncItems = []
    await nextTick()
    expect(wrapper.find('.empty-state').exists()).toBe(true)
  })

  it('forwards main drag-and-drop handlers and sidebar manage events', async () => {
    authState.isAdmin = true
    storeState.selectedFolderId = 'folder-x'
    storeState.currentFolder = { id: 'folder-x', parent_id: null, inherit_permissions: true }
    storeState.ncItems = [{ name: 'x.txt', nc_path: '/x/x.txt', is_dir: false }]

    const FilesPage = (await import('../../src/pages/FilesPage.vue')).default
    const wrapper = mount(FilesPage, { global: globalOptions })
    await flushPromises()

    await wrapper.find('.files-main').trigger('dragenter')
    await wrapper.find('.files-main').trigger('dragover')
    await wrapper.find('.files-main').trigger('dragleave')
    await wrapper.find('.files-main').trigger('drop')

    expect(uploadState.onMainDragEnter).toHaveBeenCalledTimes(1)
    expect(uploadState.onMainDragOver).toHaveBeenCalledTimes(1)
    expect(uploadState.onMainDragLeave).toHaveBeenCalledTimes(1)
    expect(uploadState.onMainDrop).toHaveBeenCalledTimes(1)

    await wrapper.findComponent(FilesSidebarStub).vm.$emit('manage-icons')
    await wrapper.findComponent(FilesSidebarStub).vm.$emit('manage-shares')
    expect(manageState.open).toHaveBeenCalledWith('file-icons')
    expect(manageState.open).toHaveBeenCalledWith('file-shares')
  })
})
