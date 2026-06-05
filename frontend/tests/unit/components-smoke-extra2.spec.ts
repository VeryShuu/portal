import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NAvatar: { template: '<div class="n-avatar"><slot /></div>', props: ['src', 'size', 'round'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'bordered'] },
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'text', 'disabled', 'loading', 'quaternary', 'circle', 'title'],
    emits: ['click'],
  },
  NSpin: { template: '<div class="n-spin" />', props: ['show'] },
  NModal: { template: '<div class="n-modal"><slot /></div>', props: ['show', 'title', 'preset'] },
  NForm: { template: '<form><slot /></form>', props: ['model', 'rules'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type', 'maxlength'],
    emits: ['update:value'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  CallOutline: { template: '<span />' },
  CopyOutline: { template: '<span />' },
  LocationOutline: { template: '<span />' },
  MailOutline: { template: '<span />' },
  PhonePortraitOutline: { template: '<span />' },
  LinkOutline: { template: '<span />' },
  ShieldCheckmarkOutline: { template: '<span />' },
  OpenOutline: { template: '<span />' },
  CreateOutline: { template: '<span />' },
  TrashOutline: { template: '<span />' },
  ReorderTwoOutline: { template: '<span />' },
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false } })),
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn() })),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {} })),
}))

vi.mock('sortablejs', () => ({
  default: {
    create: vi.fn(() => ({ destroy: vi.fn() })),
  },
}))

vi.mock('../../src/api/links', () => ({
  fetchLinks: vi.fn().mockResolvedValue({ items: [] }),
  fetchBookmarks: vi.fn().mockResolvedValue({ items: [] }),
  createBookmark: vi.fn(),
  deleteBookmark: vi.fn(),
  reorderBookmarks: vi.fn(),
  reorderLinks: vi.fn(),
}))

vi.mock('../../src/api/auth', () => ({
  fetchMe: vi.fn(),
}))

vi.mock('../../src/api/bootstrap', () => ({
  fetchBootstrap: vi.fn(),
}))

vi.mock('../../src/api', () => ({
  api: vi.fn(),
  apiUpload: vi.fn(),
  refreshAuth: vi.fn(),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/api/index', () => ({
  api: vi.fn(),
  apiUpload: vi.fn(),
  refreshAuth: vi.fn(),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/i18n', () => ({
  i18n: { global: { t: (k: string) => k } },
}))

vi.mock('../../src/styles/naive-theme', () => ({
  lightThemeOverrides: {},
  darkThemeOverrides: {},
}))

const MOCK_USER = {
  id: '00000000-0000-0000-0000-000000000001',
  full_name: 'Иван Иванов',
  email: 'ivan@example.com',
  role: 'reader' as const,
  auth_source: 'keycloak' as const,
  avatar_url: null,
  is_active: true,
  position: 'Разработчик',
  department: 'ИТ',
  phone: '+7 (999) 123-45-67',
  attributes: { mobile: '+7 (888) 000-00-00', city: 'Москва' },
}

describe('HeroBlock.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders section.hero element', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.find('section.hero').exists()).toBe(true)
  })

  it('shows greeting with user first name', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.user = { ...MOCK_USER } as any
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.text()).toContain('Иван')
  })

  it('shows custom welcome subtitle from branding', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const { useBrandingStore } = await import('../../src/stores/branding')
    const branding = useBrandingStore()
    branding.settings.welcome_subtitle = 'Добро пожаловать!'
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.text()).toContain('Добро пожаловать!')
  })

  it('renders without user logged in', async () => {
    const HeroBlock = (await import('../../src/components/HeroBlock.vue')).default
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.user = null
    const wrapper = mount(HeroBlock, { global: { plugins: [i18n] } })
    expect(wrapper.exists()).toBe(true)
  })
})

describe('StaffCard.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  const hlFn = (text: string | null | undefined) => text ?? ''

  it('renders without errors', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const wrapper = mount(StaffCard, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows user full name', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const wrapper = mount(StaffCard, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Иван Иванов')
  })

  it('shows department tag when department present', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const wrapper = mount(StaffCard, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('ИТ')
  })

  it('shows position', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const wrapper = mount(StaffCard, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Разработчик')
  })

  it('renders without phone', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const userNoPhone = { ...MOCK_USER, phone: null, attributes: {} }
    const wrapper = mount(StaffCard, {
      props: { user: userNoPhone as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders with extra attributes', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const schema = [{
      attr_key: 'team',
      label_ru: 'Команда',
      label_en: 'Team',
      sort_order: 0,
    }]
    const userWithAttrs = { ...MOCK_USER, attributes: { team: 'Бэкенд' } }
    const wrapper = mount(StaffCard, {
      props: { user: userWithAttrs as any, hl: hlFn, attributeSchema: schema as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Бэкенд')
  })

  it('shows initials when no avatar', async () => {
    const StaffCard = (await import('../../src/components/StaffCard.vue')).default
    const wrapper = mount(StaffCard, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-avatar').text()).toContain('ИИ')
  })
})

describe('StaffRow.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  const hlFn = (text: string | null | undefined) => text ?? ''

  it('renders without errors', async () => {
    const StaffRow = (await import('../../src/components/StaffRow.vue')).default
    const wrapper = mount(StaffRow, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows user full name', async () => {
    const StaffRow = (await import('../../src/components/StaffRow.vue')).default
    const wrapper = mount(StaffRow, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Иван Иванов')
  })

  it('shows position', async () => {
    const StaffRow = (await import('../../src/components/StaffRow.vue')).default
    const wrapper = mount(StaffRow, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Разработчик')
  })

  it('shows city from attributes', async () => {
    const StaffRow = (await import('../../src/components/StaffRow.vue')).default
    const wrapper = mount(StaffRow, {
      props: { user: MOCK_USER as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Москва')
  })

  it('renders without optional fields', async () => {
    const StaffRow = (await import('../../src/components/StaffRow.vue')).default
    const minimalUser = {
      id: '00000000-0000-0000-0000-000000000002',
      full_name: 'Петр Петров',
      email: 'petr@example.com',
      role: 'reader' as const,
      auth_source: 'keycloak' as const,
      avatar_url: null,
      is_active: true,
      position: null,
      department: null,
      phone: null,
      attributes: {},
    }
    const wrapper = mount(StaffRow, {
      props: { user: minimalUser as any, hl: hlFn },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Петр Петров')
  })
})

describe('LinkCard.vue', () => {
  const MOCK_LINK = {
    id: '00000000-0000-0000-0000-000000000010',
    title: 'GitHub',
    url: 'https://github.com',
    description: 'Code hosting',
    iconUrl: null,
    supportsSso: false,
    group: 'Dev',
    kind: 'link' as const,
    raw: {},
  }

  it('renders without errors', async () => {
    const LinkCard = (await import('../../src/components/links/LinkCard.vue')).default
    const wrapper = mount(LinkCard, {
      props: { item: MOCK_LINK as any, canDrag: false, isAdmin: false },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows link title', async () => {
    const LinkCard = (await import('../../src/components/links/LinkCard.vue')).default
    const wrapper = mount(LinkCard, {
      props: { item: MOCK_LINK as any, canDrag: false, isAdmin: false },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('GitHub')
  })

  it('shows drag handle when canDrag=true', async () => {
    const LinkCard = (await import('../../src/components/links/LinkCard.vue')).default
    const wrapper = mount(LinkCard, {
      props: { item: MOCK_LINK as any, canDrag: true, isAdmin: false },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.drag-handle').exists()).toBe(true)
  })

  it('no drag handle when canDrag=false', async () => {
    const LinkCard = (await import('../../src/components/links/LinkCard.vue')).default
    const wrapper = mount(LinkCard, {
      props: { item: MOCK_LINK as any, canDrag: false, isAdmin: false },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.drag-handle').exists()).toBe(false)
  })

  it('shows admin edit/delete buttons when isAdmin=true', async () => {
    const LinkCard = (await import('../../src/components/links/LinkCard.vue')).default
    const wrapper = mount(LinkCard, {
      props: { item: MOCK_LINK as any, canDrag: false, isAdmin: true },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.link-admin-actions').exists()).toBe(true)
  })

  it('renders bookmark kind', async () => {
    const LinkCard = (await import('../../src/components/links/LinkCard.vue')).default
    const bookmark = { ...MOCK_LINK, kind: 'bookmark' as const }
    const wrapper = mount(LinkCard, {
      props: { item: bookmark as any, canDrag: false, isAdmin: false },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('uses SSO redirect URL for SSO links', async () => {
    const LinkCard = (await import('../../src/components/links/LinkCard.vue')).default
    const ssoLink = { ...MOCK_LINK, supportsSso: true }
    const wrapper = mount(LinkCard, {
      props: { item: ssoLink as any, canDrag: false, isAdmin: false },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('a').attributes('href')).toContain('sso-redirect')
  })
})

describe('BookmarksTab.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const BookmarksTab = (await import('../../src/components/links/BookmarksTab.vue')).default
    const wrapper = mount(BookmarksTab, { global: { plugins: [i18n] } })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows empty state when no bookmarks', async () => {
    const BookmarksTab = (await import('../../src/components/links/BookmarksTab.vue')).default
    const { useLinksStore } = await import('../../src/stores/links')
    const store = useLinksStore()
    store.bookmarks = []
    const wrapper = mount(BookmarksTab, { global: { plugins: [i18n] } })
    expect(wrapper.find('.empty-state, [class*="empty"]').exists() || wrapper.html().includes('EmptyState') || !wrapper.find('.links-grid').exists()).toBe(true)
  })

  it('does not show loading spinner when not loading', async () => {
    const BookmarksTab = (await import('../../src/components/links/BookmarksTab.vue')).default
    const { useLinksStore } = await import('../../src/stores/links')
    const store = useLinksStore()
    store.loadingBookmarks = false
    const wrapper = mount(BookmarksTab, { global: { plugins: [i18n] } })
    expect(wrapper.find('.n-spin').exists()).toBe(false)
  })
})
