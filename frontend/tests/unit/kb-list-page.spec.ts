import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { computed, ref, nextTick, type Ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

type KbPermission = 'viewer' | 'editor' | 'manager' | null

type SectionNode = {
  id: string
  title: string
  children: SectionNode[]
  user_permission?: KbPermission
}

type ArticleItem = {
  id: string
  title: string
}

const mockRouterPush = vi.fn()
const mockRouterBack = vi.fn()
const mockRouterReplace = vi.fn()

const mockManageOpen = vi.fn()
const mockManageClose = vi.fn()
const mockManageIs = vi.fn(() => false)

const mockExportSectionZip = vi.fn()

const mockAuthState: {
  isAdmin: boolean
  isEditor: boolean
  user: { id: string; role: string }
} = {
  isAdmin: false,
  isEditor: false,
  user: { id: 'user-1', role: 'reader' },
}

function makeSection(id: string, user_permission: KbPermission = null, children: SectionNode[] = []): SectionNode {
  return {
    id,
    title: `Section ${id}`,
    children,
    user_permission,
  }
}

type SectionsCtl = {
  sections: Ref<SectionNode[]>
  sectionsLoading: Ref<boolean>
  selectedSection: Ref<string | null>
  showSectionModal: Ref<boolean>
  sectionSaving: Ref<boolean>
  sectionForm: Ref<{ title: string; description: string; parent_id: string | null }>
  showSectionPermsModal: Ref<boolean>
  sectionPermsId: Ref<string | null>
  sectionPermsInherit: Ref<boolean>
  onSectionInheritChanged: ReturnType<typeof vi.fn>
  showMoveModal: Ref<boolean>
  moveSectionId: Ref<string | null>
  moveSaving: Ref<boolean>
  openSectionPermissions: ReturnType<typeof vi.fn>
  openCreateSection: ReturnType<typeof vi.fn>
  openMoveSection: ReturnType<typeof vi.fn>
  submitMoveSection: ReturnType<typeof vi.fn>
  submitCreateSection: ReturnType<typeof vi.fn>
  renameSection: ReturnType<typeof vi.fn>
  confirmDeleteSection: ReturnType<typeof vi.fn>
}

let mockSectionsCtl: SectionsCtl

function createSectionsCtl(params?: {
  selectedSection?: string | null
  sections?: SectionNode[]
}): SectionsCtl {
  return {
    sections: ref(params?.sections ?? [makeSection('sec-1', 'editor'), makeSection('sec-2', 'viewer')]),
    sectionsLoading: ref(false),
    selectedSection: ref(params?.selectedSection ?? null),
    showSectionModal: ref(false),
    sectionSaving: ref(false),
    sectionForm: ref({ title: '', description: '', parent_id: null }),
    showSectionPermsModal: ref(false),
    sectionPermsId: ref(null),
    sectionPermsInherit: ref(true),
    onSectionInheritChanged: vi.fn(),
    showMoveModal: ref(false),
    moveSectionId: ref(null),
    moveSaving: ref(false),
    openSectionPermissions: vi.fn(),
    openCreateSection: vi.fn(),
    openMoveSection: vi.fn(),
    submitMoveSection: vi.fn(),
    submitCreateSection: vi.fn(),
    renameSection: vi.fn(),
    confirmDeleteSection: vi.fn(),
  }
}

function createListing(selectedSection: Ref<string | null>) {
  const page = ref(1)
  const searchQuery = ref('')
  const statusFilter = ref<string | null>(null)
  const tagFilter = ref<string | null>(null)
  const loading = ref(false)
  const allArticles = ref<ArticleItem[]>([
    { id: 'art-1', title: 'Article 1' },
    { id: 'art-2', title: 'Article 2' },
  ])

  const articles = computed(() => {
    if (selectedSection.value === 'sec-1') return [allArticles.value[0]]
    if (selectedSection.value === 'sec-2') return [allArticles.value[1]]
    return allArticles.value
  })

  const total = computed(() => articles.value.length)

  return {
    page,
    pageSize: 20,
    searchQuery,
    statusFilter,
    tagFilter,
    articles,
    total,
    loading,
    tagOptions: ref([] as Array<{ label: string; value: string }>),
    selectTag: vi.fn(),
    onSearchInput: vi.fn(),
  }
}

const mockUseKbSections = vi.fn(() => mockSectionsCtl)
const mockUseKbArticleListing = vi.fn((opts: { selectedSection: Ref<string | null> }) => createListing(opts.selectedSection))

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" :title="title" @click="$emit(\'click\')"><slot name="icon" /><slot /></button>',
    props: ['type', 'size', 'loading', 'disabled', 'quaternary', 'circle', 'title'],
    emits: ['click'],
  },
  NPagination: {
    template: '<div class="n-pagination" />',
    props: ['page', 'pageCount'],
    emits: ['update:page'],
  },
  NDrawer: {
    template: '<div v-if="show" class="n-drawer"><slot /></div>',
    props: ['show', 'width', 'placement', 'onUpdateShow'],
  },
  NDrawerContent: {
    template: '<div class="n-drawer-content"><slot /></div>',
    props: ['title', 'closable'],
  },
  NIcon: {
    template: '<span class="n-icon"><slot /></span>',
    props: ['component'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({
    push: (...args: unknown[]) => mockRouterPush(...args),
    back: (...args: unknown[]) => mockRouterBack(...args),
    replace: (...args: unknown[]) => mockRouterReplace(...args),
  })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  SettingsOutline: { template: '<span />' },
  TrashOutline: { template: '<span />' },
}))

vi.mock('../../src/composables/useManageDrawer', () => ({
  useManageDrawer: vi.fn(() => ({
    open: (...args: unknown[]) => mockManageOpen(...args),
    close: (...args: unknown[]) => mockManageClose(...args),
    is: (...args: unknown[]) => mockManageIs(...args),
  })),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => mockAuthState),
}))

vi.mock('../../src/api/kb', () => ({
  exportSectionZip: (...args: unknown[]) => mockExportSectionZip(...args),
}))

vi.mock('../../src/composables/useKbSections', () => ({
  useKbSections: (...args: unknown[]) => mockUseKbSections(...args),
  findSectionRecursive: (nodes: SectionNode[], id: string): SectionNode | null => {
    for (const n of nodes) {
      if (n.id === id) return n
      const found = n.children.length ? ((): SectionNode | null => {
        const stack = [...n.children]
        while (stack.length) {
          const cur = stack.shift()!
          if (cur.id === id) return cur
          if (cur.children.length) stack.push(...cur.children)
        }
        return null
      })() : null
      if (found) return found
    }
    return null
  },
}))

vi.mock('../../src/pages/admin/tabs/KbTab.vue', () => ({
  default: {
    template: '<div class="kb-admin-tab-stub" />',
  },
}))

vi.mock('../../src/composables/useKbArticleListing', () => ({
  useKbArticleListing: (...args: unknown[]) => mockUseKbArticleListing(...args),
}))

const globalOptions = {
  plugins: [i18n],
  stubs: {
    SkeletonCard: {
      template: '<div class="skeleton-card" />',
      props: ['variant'],
    },
    EmptyState: {
      template: '<div class="empty-state" />',
      props: ['variant', 'title', 'description'],
    },
    KbListToolbar: {
      template: '<div class="kb-list-toolbar-stub"><button class="toolbar-grid" @click="$emit(\'update:view-mode\', \'grid\')">grid</button><button class="toolbar-list" @click="$emit(\'update:view-mode\', \'list\')">list</button><button class="toolbar-search" @click="$emit(\'search-input\')">search</button></div>',
      props: ['searchQuery', 'statusFilter', 'tagFilter', 'tagOptions', 'viewMode'],
      emits: ['update:view-mode', 'search-input', 'update:search-query', 'update:status-filter', 'update:tag-filter'],
    },
    KbSectionTree: {
      template: '<button class="kb-section-tree-stub" :data-id="section.id" @click="$emit(\'select\', section.id)">{{ section.title }}</button>',
      props: ['section', 'activeId', 'isAdmin'],
      emits: ['select', 'add-child', 'rename-section', 'manage-permissions', 'move-section', 'delete-section'],
    },
    KbPermissionsModal: {
      template: '<div class="kb-permissions-modal-stub" />',
      props: ['modelValue', 'resourceType', 'resourceId', 'inheritPermissions'],
      emits: ['update:modelValue', 'inherit-changed'],
    },
    KbSectionMoveModal: {
      template: '<div class="kb-section-move-modal-stub" />',
      props: ['show', 'sectionId', 'sections', 'saving'],
      emits: ['update:show', 'submit'],
    },
    KbSectionFormModal: {
      template: '<div class="kb-section-form-modal-stub" />',
      props: ['show', 'form', 'saving'],
      emits: ['update:show', 'update:form', 'submit'],
    },
    KbImportModal: {
      template: '<div class="kb-import-modal-stub" />',
      props: ['show'],
      emits: ['update:show', 'imported'],
    },
    KbArticleCard: {
      template: '<div class="article-card-stub"><button class="card-open" @click="$emit(\'open\', article)">open</button><button class="card-tag" @click="$emit(\'select-tag\', \'tag-1\')">tag</button></div>',
      props: ['article', 'activeTag'],
      emits: ['open', 'select-tag'],
    },
    KbArticleListRow: {
      template: '<div class="article-row-stub"><button class="row-open" @click="$emit(\'open\', article)">open</button><button class="row-tag" @click="$emit(\'select-tag\', \'tag-1\')">tag</button></div>',
      props: ['article', 'activeTag'],
      emits: ['open', 'select-tag'],
    },
  },
}

function setupAuth(params: { isAdmin: boolean; isEditor: boolean; role: string }) {
  mockAuthState.isAdmin = params.isAdmin
  mockAuthState.isEditor = params.isEditor
  mockAuthState.user = { id: 'user-1', role: params.role }
}

function setupSections(params?: { selectedSection?: string | null; sections?: SectionNode[] }) {
  mockSectionsCtl = createSectionsCtl(params)
}

async function mountPage() {
  const KbListPage = (await import('../../src/pages/KbListPage.vue')).default
  const wrapper = mount(KbListPage, { global: globalOptions })
  await flushPromises()
  return wrapper
}

describe('KbListPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setupAuth({ isAdmin: false, isEditor: false, role: 'reader' })
    setupSections()
    mockRouterPush.mockClear()
    mockRouterBack.mockClear()
    mockRouterReplace.mockClear()
    mockManageOpen.mockClear()
    mockManageClose.mockClear()
    mockManageIs.mockClear()
    mockManageIs.mockReturnValue(false)
    mockExportSectionZip.mockClear()
    mockUseKbSections.mockClear()
    mockUseKbArticleListing.mockClear()
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('shows admin actions and opens manage drawer when admin settings button clicked', async () => {
    setupAuth({ isAdmin: true, isEditor: true, role: 'admin' })
    setupSections({ selectedSection: 'sec-1' })
    const wrapper = await mountPage()

    const actions = wrapper.find('.u-page-head__actions')
    expect(actions.find('.n-button[title="admin.tabs.kb"]').exists()).toBe(true)
    expect(actions.find('.n-button[title="kb.trash.openTitle"]').exists()).toBe(true)
    expect(actions.text()).toContain('kb.import.title')
    expect(actions.text()).toContain('kb.createArticle')

    await actions.find('.n-button[title="admin.tabs.kb"]').trigger('click')
    expect(mockManageOpen).toHaveBeenCalledWith('kb')
  })

  it('shows import and create but hides admin actions for non-admin editor', async () => {
    setupAuth({ isAdmin: false, isEditor: true, role: 'editor' })
    const wrapper = await mountPage()

    const actions = wrapper.find('.u-page-head__actions')
    expect(actions.find('.n-button[title="admin.tabs.kb"]').exists()).toBe(false)
    expect(actions.find('.n-button[title="kb.trash.openTitle"]').exists()).toBe(false)
    expect(actions.text()).toContain('kb.import.title')
    expect(actions.text()).toContain('kb.createArticle')
  })

  it('shows create button for regular user when no section is selected', async () => {
    setupAuth({ isAdmin: false, isEditor: false, role: 'reader' })
    setupSections({ selectedSection: null })
    const wrapper = await mountPage()

    expect(wrapper.find('.u-page-head__actions').text()).toContain('kb.createArticle')
  })

  it('hides create button for regular user in selected viewer-only section', async () => {
    setupAuth({ isAdmin: false, isEditor: false, role: 'reader' })
    setupSections({
      selectedSection: 'sec-view',
      sections: [makeSection('sec-view', 'viewer')],
    })
    const wrapper = await mountPage()

    expect(wrapper.find('.u-page-head__actions').text()).not.toContain('kb.createArticle')
  })

  it('shows create button for regular user in selected manager section', async () => {
    setupAuth({ isAdmin: false, isEditor: false, role: 'reader' })
    setupSections({
      selectedSection: 'sec-manage',
      sections: [makeSection('sec-manage', 'manager')],
    })
    const wrapper = await mountPage()

    expect(wrapper.find('.u-page-head__actions').text()).toContain('kb.createArticle')
  })

  it('navigates to kb-trash when admin clicks trash button', async () => {
    setupAuth({ isAdmin: true, isEditor: true, role: 'admin' })
    const wrapper = await mountPage()

    await wrapper.find('.n-button[title="kb.trash.openTitle"]').trigger('click')
    expect(mockRouterPush).toHaveBeenCalledWith({ name: 'kb-trash' })
  })

  it('navigates to create route with selected section id in query', async () => {
    setupSections({ selectedSection: 'sec-1' })
    const wrapper = await mountPage()

    const actionButtons = wrapper.findAll('.u-page-head__actions .n-button')
    const createButton = actionButtons[actionButtons.length - 1]
    await createButton.trigger('click')

    expect(mockRouterPush).toHaveBeenCalledWith({
      path: '/kb/create',
      query: { section_id: 'sec-1' },
    })
  })

  it('navigates to article details when list row emits open', async () => {
    const wrapper = await mountPage()

    const openButtons = wrapper.findAll('.article-row-stub .row-open')
    expect(openButtons.length).toBe(2)
    await openButtons[0].trigger('click')

    expect(mockRouterPush).toHaveBeenCalledWith('/kb/articles/art-1')
  })

  it('exports selected section when export action is clicked', async () => {
    setupSections({ selectedSection: 'sec-1' })
    const wrapper = await mountPage()

    const actionButtons = wrapper.findAll('.u-page-head__actions .n-button')
    const exportButton = actionButtons.find((b) => b.text().includes('kb.export.sectionZip'))
    expect(exportButton).toBeDefined()
    await exportButton!.trigger('click')

    expect(mockExportSectionZip).toHaveBeenCalledWith('sec-1')
  })

  it('reads initial view mode from localStorage and renders grid', async () => {
    localStorage.setItem('kb:viewMode', 'grid')
    const wrapper = await mountPage()

    expect(wrapper.find('.kb-grid').exists()).toBe(true)
    expect(wrapper.findAll('.article-card-stub').length).toBe(2)
  })

  it('persists view mode to localStorage on toolbar update:view-mode', async () => {
    localStorage.setItem('kb:viewMode', 'grid')
    const wrapper = await mountPage()

    await wrapper.find('.kb-list-toolbar-stub .toolbar-list').trigger('click')
    await nextTick()

    expect(localStorage.getItem('kb:viewMode')).toBe('list')
    expect(wrapper.find('.kb-list').exists()).toBe(true)
    expect(wrapper.findAll('.article-row-stub').length).toBe(2)
  })

  it('syncs section tree selection with listing and all-articles reset', async () => {
    setupSections({
      selectedSection: null,
      sections: [makeSection('sec-1', 'editor'), makeSection('sec-2', 'viewer')],
    })
    const wrapper = await mountPage()

    expect(wrapper.findAll('.article-row-stub').length).toBe(2)
    expect(wrapper.find('.u-page-head__actions').text()).not.toContain('kb.export.sectionZip')

    await wrapper.find('.kb-section-tree-stub[data-id="sec-1"]').trigger('click')
    await nextTick()

    expect(mockSectionsCtl.selectedSection.value).toBe('sec-1')
    expect(wrapper.findAll('.article-row-stub').length).toBe(1)
    expect(wrapper.find('.u-page-head__actions').text()).toContain('kb.export.sectionZip')

    await wrapper.find('.kb-tree__item').trigger('click')
    await nextTick()

    expect(mockSectionsCtl.selectedSection.value).toBeNull()
    expect(wrapper.findAll('.article-row-stub').length).toBe(2)
    expect(wrapper.find('.u-page-head__actions').text()).not.toContain('kb.export.sectionZip')
  })
})
