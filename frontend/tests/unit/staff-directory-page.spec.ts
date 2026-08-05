import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, defineComponent, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import type { UserPublic } from '../../src/api/users'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'loading', 'text', 'secondary'],
    emits: ['click'],
  },
  NPagination: {
    template: '<div class="n-pagination" />',
    props: ['page', 'pageCount', 'pageSlot'],
    emits: ['update:page'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
  useDialog: () => ({ warning: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/', name: 'home' })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
  onBeforeRouteLeave: vi.fn(),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), setQueryData: vi.fn() })),
}))

vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

const mockSyncToUrl = vi.fn()
const mockOnSearchInput = vi.fn()
const mockOnFilterChange = vi.fn()
const mockResetFilters = vi.fn()
const mockSearchInput = ref('')
const mockQ = ref('')
const mockDepartmentFilter = ref<string | null>(null)
const mockOfficeFilter = ref<string | null>(null)
const mockPage = ref(1)
const mockHasActiveFilters = ref(false)

vi.mock('../../src/composables/useStaffFilters', () => ({
  useStaffFilters: vi.fn(() => ({
    searchInput: mockSearchInput,
    q: mockQ,
    departmentFilter: mockDepartmentFilter,
    officeFilter: mockOfficeFilter,
    page: mockPage,
    hasActiveFilters: mockHasActiveFilters,
    onSearchInput: mockOnSearchInput,
    onFilterChange: mockOnFilterChange,
    resetFilters: mockResetFilters,
    onPageChange: vi.fn(),
    syncToUrl: mockSyncToUrl,
    debouncedApplySearch: vi.fn(),
  })),
}))

vi.mock('../../src/composables/useStaffEdit', () => ({
  useStaffEdit: vi.fn(() => ({
    editMode: ref(false),
    editGroups: ref([]),
    dirty: ref(false),
    saving: ref(false),
    enterEdit: vi.fn(),
    cancelEdit: vi.fn(),
    saveEdit: vi.fn(),
    toggleUserHidden: vi.fn(),
    destroySortables: vi.fn(),
  })),
}))

vi.mock('../../src/composables/useStaffView', () => ({
  useStaffView: vi.fn(() => ({
    view: ref('grid'),
    effectiveView: ref('grid'),
    setView: vi.fn(),
    isMobile: ref(false),
  })),
}))

vi.mock('../../src/composables/useStaffExport', () => ({
  useStaffExport: vi.fn(() => ({
    onExport: vi.fn(),
    onPrint: vi.fn(),
  })),
}))

vi.mock('../../src/composables/useStaffLeaveGuard', () => ({
  useStaffLeaveGuard: vi.fn(),
}))

vi.mock('../../src/composables/useHighlight', () => ({
  useHighlight: vi.fn(() => (text: string | null | undefined) => text ?? ''),
}))

const mockStaffListQuery = vi.fn(() => ({
  data: ref(undefined),
  isLoading: ref(false),
  isFetching: ref(false),
}))

vi.mock('../../src/queries/users', () => ({
  useStaffListQuery: (...args: unknown[]) => mockStaffListQuery(...args),
  useUserDepartmentsQuery: vi.fn(() => ({ data: ref({ items: [] }) })),
  useUserOfficesQuery: vi.fn(() => ({ data: ref({ items: [] }) })),
  useUserAttributeSchemaQuery: vi.fn(() => ({ data: ref({ items: [] }) })),
  useStaffSettingsQuery: vi.fn(() => ({ data: ref({ phone_extract_regex: '' }) })),
}))

vi.mock('../../src/queries/directories', () => ({
  useDirectoriesQuery: vi.fn(() => ({ data: ref({ items: [], total: 0 }) })),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({
    isAdmin: false,
    isEditor: false,
  })),
}))

const StaffFiltersStub = defineComponent({
  name: 'StaffFilters',
  props: {
    searchInput: { type: String, default: '' },
    departmentFilter: { type: String, default: null },
    officeFilter: { type: String, default: null },
    departmentOptions: { type: Array, default: () => [] },
    officeOptions: { type: Array, default: () => [] },
    hasActiveFilters: { type: Boolean, default: false },
    view: { type: String, default: 'grid' },
    effectiveView: { type: String, default: 'grid' },
    isMobile: { type: Boolean, default: false },
    isAdmin: { type: Boolean, default: false },
    editMode: { type: Boolean, default: false },
    dirty: { type: Boolean, default: false },
    saving: { type: Boolean, default: false },
  },
  emits: ['change-search', 'change-department', 'change-office', 'reset', 'set-view', 'enter-edit', 'export', 'print', 'cancel-edit', 'save-edit'],
  template: '<div class="staff-filters-stub" />',
})

const globalOptions = {
  plugins: [i18n],
  stubs: {
    StaffFilters: StaffFiltersStub,
    StaffGridView: { template: '<div class="staff-grid-stub" />', props: ['users', 'hl', 'attributeSchema', 'lang', 'isFetching'] },
    StaffTableView: { template: '<div class="staff-table-view-stub" />', props: ['tableGroups', 'hl', 'isFetching'] },
    StaffEditView: { template: '<div class="staff-edit-view-stub" />', props: ['editGroups'] },
    EmptyState: { template: '<div class="empty-state"><slot /><slot name="action" /></div>', props: ['variant', 'title', 'description'] },
    SkeletonCard: { template: '<div class="skeleton-card" />', props: ['variant'] },
  },
}

function makeUser(overrides: Partial<UserPublic> = {}): UserPublic {
  return {
    id: 'u1',
    email: 'ivan@example.com',
    full_name: 'Иван Иванов',
    department: 'IT',
    position: 'Developer',
    phone: '101',
    role: 'reader',
    avatar_url: null,
    current_status: 'working', current_status_until: null,
    lang: 'ru',
    created_at: '2024-01-01T00:00:00Z',
    auth_source: 'keycloak',
    attributes: {},
    last_login_at: null,
    ...overrides,
  }
}

describe('StaffDirectoryPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockSearchInput.value = ''
    mockQ.value = ''
    mockDepartmentFilter.value = null
    mockOfficeFilter.value = null
    mockPage.value = 1
    mockHasActiveFilters.value = false
    mockSyncToUrl.mockClear()
    mockOnSearchInput.mockClear()
    mockOnFilterChange.mockClear()
    mockResetFilters.mockClear()
    mockStaffListQuery.mockReturnValue({
      data: ref(undefined),
      isLoading: ref(false),
      isFetching: ref(false),
    })
  })

  it('renders empty state when query returns no staff', async () => {
    mockStaffListQuery.mockReturnValue({
      data: ref({ items: [], total: 0 }),
      isLoading: ref(false),
      isFetching: ref(false),
    })
    const StaffDirectoryPage = (await import('../../src/pages/StaffDirectoryPage.vue')).default
    const wrapper = mount(StaffDirectoryPage, { global: globalOptions })

    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(wrapper.find('.staff-grid-stub').exists()).toBe(false)
    expect(wrapper.find('.skeleton-card').exists()).toBe(false)
  })

  it('renders skeleton cards during initial loading', async () => {
    mockStaffListQuery.mockReturnValue({
      data: ref(undefined),
      isLoading: ref(true),
      isFetching: ref(false),
    })
    const StaffDirectoryPage = (await import('../../src/pages/StaffDirectoryPage.vue')).default
    const wrapper = mount(StaffDirectoryPage, { global: globalOptions })

    expect(wrapper.findAll('.skeleton-card').length).toBe(6)
    expect(wrapper.find('.staff-grid-stub').exists()).toBe(false)
    expect(wrapper.find('.empty-state').exists()).toBe(false)
  })

  it('renders staff grid when data is available', async () => {
    const user = makeUser()
    mockStaffListQuery.mockReturnValue({
      data: ref({ items: [user], total: 1 }),
      isLoading: ref(false),
      isFetching: ref(false),
    })
    const StaffDirectoryPage = (await import('../../src/pages/StaffDirectoryPage.vue')).default
    const wrapper = mount(StaffDirectoryPage, { global: globalOptions })

    expect(wrapper.find('.staff-grid-stub').exists()).toBe(true)
    expect(wrapper.find('.empty-state').exists()).toBe(false)
    expect(wrapper.find('.skeleton-card').exists()).toBe(false)
  })

  it('calls onSearchChange when StaffFilters emits change-search', async () => {
    mockStaffListQuery.mockReturnValue({
      data: ref({ items: [], total: 0 }),
      isLoading: ref(false),
      isFetching: ref(false),
    })
    const StaffDirectoryPage = (await import('../../src/pages/StaffDirectoryPage.vue')).default
    const wrapper = mount(StaffDirectoryPage, { global: globalOptions })

    const filtersStub = wrapper.findComponent(StaffFiltersStub)
    await filtersStub.vm.$emit('change-search', 'alice')
    await nextTick()

    expect(mockSearchInput.value).toBe('alice')
    expect(mockOnSearchInput).toHaveBeenCalled()
  })

  it('StaffFilters receives correct filter props from state', async () => {
    mockSearchInput.value = 'test'
    mockDepartmentFilter.value = 'Engineering'
    mockHasActiveFilters.value = true

    mockStaffListQuery.mockReturnValue({
      data: ref({ items: [], total: 0 }),
      isLoading: ref(false),
      isFetching: ref(false),
    })
    const StaffDirectoryPage = (await import('../../src/pages/StaffDirectoryPage.vue')).default
    const wrapper = mount(StaffDirectoryPage, { global: globalOptions })

    const filtersStub = wrapper.findComponent(StaffFiltersStub)
    expect(filtersStub.props('searchInput')).toBe('test')
    expect(filtersStub.props('departmentFilter')).toBe('Engineering')
    expect(filtersStub.props('hasActiveFilters')).toBe(true)
  })

  it('calls syncToUrl on mount', async () => {
    const StaffDirectoryPage = (await import('../../src/pages/StaffDirectoryPage.vue')).default
    mount(StaffDirectoryPage, { global: globalOptions })

    expect(mockSyncToUrl).toHaveBeenCalled()
  })
})
