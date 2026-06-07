import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref, defineComponent, nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const routeState = ref<any>({ name: 'user-profile', params: { id: 'u2' }, query: {}, path: '/users/u2' })
const routerReplace = vi.fn()
const routerBack = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => routeState.value,
  useRouter: () => ({ replace: routerReplace, back: routerBack, push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
  onBeforeRouteLeave: vi.fn(),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false }, isFetching: { value: false }, error: { value: null }, refetch: vi.fn() })),
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: { value: false }, isError: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn(), setQueryData: vi.fn() })),
  useInfiniteQuery: vi.fn(() => ({ data: { value: { pages: [] } }, isLoading: { value: false }, fetchNextPage: vi.fn(), hasNextPage: { value: false } })),
  keepPreviousData: undefined,
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({ data: {} }),
  apiUpload: vi.fn().mockResolvedValue({ data: {} }),
  BASE_URL: '/api/v1',
}))

const NButtonStub = { template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'disabled', 'loading'], emits: ['click'] }
const NPaginationStub = { template: '<div class="n-pagination" />', props: ['page', 'pageCount', 'pageSize'], emits: ['update:page'] }

vi.mock('naive-ui', () => ({
  NButton: NButtonStub,
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NResult: { template: '<div class="n-result"><slot name="footer" /></div>', props: ['status', 'title', 'description'] },
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated'], emits: ['update:value'] },
  NTab: { template: '<div class="n-tab"><slot /></div>', props: ['name'] },
  NPagination: NPaginationStub,
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
  useDialog: () => ({ warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))
vi.mock('@vicons/fluent', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

const authStore = {
  user: null as any,
  isAdmin: false,
  isLocalUser: false,
  isEditor: false,
}

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => authStore,
}))

const userQueryMock = vi.fn()
const attrSchemaQueryMock = vi.fn()
const groupsQueryMock = vi.fn()
const staffListQueryMock = vi.fn()

vi.mock('../../src/queries/users', () => ({
  useUserQuery: (...args: unknown[]) => userQueryMock(...args),
  useUserAttributeSchemaQuery: (...args: unknown[]) => attrSchemaQueryMock(...args),
  useUserKeycloakGroupsQuery: (...args: unknown[]) => groupsQueryMock(...args),
  useStaffListQuery: (...args: unknown[]) => staffListQueryMock(...args),
  useUserDepartmentsQuery: vi.fn(() => ({ data: ref({ items: [] }) })),
  useUserOfficesQuery: vi.fn(() => ({ data: ref({ items: [] }) })),
}))

vi.mock('../../src/queries/directories', () => ({
  useDirectoriesQuery: vi.fn(() => ({ data: ref({ items: [] }) })),
}))

const modulesStore = { isEnabled: vi.fn(() => true) }
vi.mock('../../src/stores/modules', () => ({
  useModulesStore: () => modulesStore,
}))

const staffFiltersState = {
  searchInput: ref(''),
  q: ref(''),
  departmentFilter: ref<string | null>(null),
  officeFilter: ref<string | null>(null),
  page: ref(1),
  hasActiveFilters: ref(false),
  onSearchInput: vi.fn(),
  onFilterChange: vi.fn(),
  resetFilters: vi.fn(),
  onPageChange: vi.fn(),
  syncToUrl: vi.fn(),
}

const staffEditState = {
  editMode: ref(false),
  editGroups: ref<any[]>([]),
  dirty: ref(false),
  saving: ref(false),
  enterEdit: vi.fn(),
  cancelEdit: vi.fn(),
  saveEdit: vi.fn(),
  toggleUserHidden: vi.fn(),
  destroySortables: vi.fn(),
}

const staffViewState = {
  view: ref<'grid' | 'table'>('grid'),
  effectiveView: ref<'grid' | 'table'>('grid'),
  setView: vi.fn(),
  isMobile: ref(false),
}

vi.mock('../../src/composables/useStaffFilters', () => ({
  useStaffFilters: () => staffFiltersState,
}))
vi.mock('../../src/composables/useStaffEdit', () => ({
  useStaffEdit: () => staffEditState,
}))
vi.mock('../../src/composables/useStaffView', () => ({
  useStaffView: () => staffViewState,
}))
vi.mock('../../src/composables/useStaffExport', () => ({
  useStaffExport: () => ({ onExport: vi.fn(), onPrint: vi.fn() }),
}))
vi.mock('../../src/composables/useStaffLeaveGuard', () => ({
  useStaffLeaveGuard: vi.fn(),
}))
vi.mock('../../src/composables/useHighlight', () => ({
  useHighlight: () => (text: string | null | undefined) => text ?? '',
}))

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
    ProfileHero: { template: '<div class="profile-hero" />', props: ['user', 'isOwn'] },
    ProfileInfoCard: { template: '<div class="profile-info" />', props: ['user', 'isOwn', 'extraAttributes'] },
    ProfileGroupsCard: { template: '<div class="profile-groups" />', props: ['groups', 'loading'] },
    ProfilePreferencesCard: { template: '<div class="profile-preferences" />' },
    ProfilePasswordCard: { template: '<div class="profile-password" />' },
    DepartmentColleagues: { template: '<div class="profile-colleagues" />', props: ['department', 'excludeUserId'] },
    DirectoryTab: { template: '<div class="directory-tab" />', props: ['directory', 'lang'] },
    StaffFilters: defineComponent({ template: '<div class="staff-filters" />' }),
    StaffGridView: { template: '<div class="staff-grid" />', props: ['users', 'hl', 'attributeSchema', 'lang', 'isFetching'] },
    StaffTableView: { template: '<div class="staff-table" />', props: ['tableGroups', 'hl', 'isFetching'] },
    StaffEditView: { template: '<div class="staff-edit" />', props: ['editGroups'] },
    EmptyState: { template: '<div class="empty-state"><slot /><slot name="action" /></div>', props: ['variant', 'title', 'description'] },
    SkeletonCard: { template: '<div class="skeleton-card" />' },
  },
}

describe('UserProfileView.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    authStore.user = null
    authStore.isAdmin = false
    authStore.isLocalUser = false
    routeState.value = { name: 'user-profile', params: { id: 'u2' }, query: {}, path: '/users/u2' }
    userQueryMock.mockReturnValue({ data: ref(null), isLoading: ref(false) })
    attrSchemaQueryMock.mockReturnValue({ data: ref({ items: [] }) })
    groupsQueryMock.mockReturnValue({ data: ref({ groups: [] }), isLoading: ref(false) })
  })

  it('shows loading spinner while profile query is loading', async () => {
    userQueryMock.mockReturnValue({ data: ref(null), isLoading: ref(true) })
    const UserProfileView = (await import('../../src/pages/UserProfileView.vue')).default
    const wrapper = mount(UserProfileView, { global: globalPlugins })
    expect(wrapper.find('.n-spin').exists()).toBe(true)
  })

  it('renders not-found result when queried user is absent', async () => {
    const UserProfileView = (await import('../../src/pages/UserProfileView.vue')).default
    const wrapper = mount(UserProfileView, { global: globalPlugins })

    expect(wrapper.find('.n-result').exists()).toBe(true)
  })

  it('renders own profile blocks for local users', async () => {
    routeState.value = { name: 'profile', params: {}, query: {}, path: '/profile' }
    authStore.user = {
      id: 'u1',
      full_name: 'Own User',
      email: 'own@example.com',
      department: 'IT',
      attributes: {},
      lang: 'ru',
    }
    authStore.isAdmin = true
    authStore.isLocalUser = true

    const UserProfileView = (await import('../../src/pages/UserProfileView.vue')).default
    const wrapper = mount(UserProfileView, { global: globalPlugins })

    expect(wrapper.find('.profile-hero').exists()).toBe(true)
    expect(wrapper.find('.profile-preferences').exists()).toBe(true)
    expect(wrapper.find('.profile-password').exists()).toBe(true)
    expect(wrapper.find('.profile-groups').exists()).toBe(true)
  })
})

describe('StaffDirectoryPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    routeState.value = { name: 'staff', params: {}, query: {}, path: '/staff' }
    staffFiltersState.syncToUrl.mockClear()
    staffViewState.effectiveView.value = 'grid'
    staffEditState.editMode.value = false
    staffListQueryMock.mockReturnValue({
      data: ref({ items: [], total: 0 }),
      isLoading: ref(false),
      isFetching: ref(false),
    })
  })

  it('renders directory tab when query points to an existing directory', async () => {
    routeState.value = { name: 'staff', params: {}, query: { tab: 'people' }, path: '/staff' }
    const { useDirectoriesQuery } = await import('../../src/queries/directories')
    vi.mocked(useDirectoriesQuery).mockReturnValue({ data: ref({ items: [{ slug: 'people', label_ru: 'Люди', label_en: 'People' }] }) } as never)

    const StaffDirectoryPage = (await import('../../src/pages/StaffDirectoryPage.vue')).default
    const wrapper = mount(StaffDirectoryPage, { global: globalPlugins })

    expect(wrapper.find('.directory-tab').exists()).toBe(true)
  })

  it('renders empty state when no users are available in staff tab', async () => {
    const StaffDirectoryPage = (await import('../../src/pages/StaffDirectoryPage.vue')).default
    const wrapper = mount(StaffDirectoryPage, { global: globalPlugins })

    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(staffFiltersState.syncToUrl).toHaveBeenCalled()
  })

  it('renders table view when effective view is table and users exist', async () => {
    staffViewState.effectiveView.value = 'table'
    staffListQueryMock.mockReturnValue({
      data: ref({ items: [{ id: 'u1', full_name: 'A', email: 'a@x.com', department: 'IT' }], total: 1 }),
      isLoading: ref(false),
      isFetching: ref(false),
    })

    const StaffDirectoryPage = (await import('../../src/pages/StaffDirectoryPage.vue')).default
    const wrapper = mount(StaffDirectoryPage, { global: globalPlugins })
    await nextTick()

    expect(wrapper.find('.staff-table').exists()).toBe(true)
    expect(wrapper.find('.staff-grid').exists()).toBe(false)
  })
})
