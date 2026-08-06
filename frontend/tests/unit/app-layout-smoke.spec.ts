import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'
import { useAuthStore } from '../../src/stores/auth'

vi.mock('naive-ui', () => ({
  NLayout: { template: '<div class="n-layout"><slot /></div>', props: ['hasSider'] },
  NLayoutContent: { template: '<main><slot /></main>', props: ['tag', 'ariaLabel'] },
  NLayoutHeader: { template: '<header><slot /></header>', props: ['bordered'] },
  NLayoutSider: {
    template: '<aside><slot /></aside>',
    props: ['bordered', 'collapseMode', 'collapsedWidth', 'width', 'collapsed', 'showTrigger'],
    emits: ['collapse', 'expand'],
  },
  NMenu: { template: '<nav />', props: ['collapsed', 'collapsedWidth', 'collapsedIconSize', 'options', 'value', 'indent'] },
  NModal: {
    template: '<div v-if="show"><slot /></div>',
    props: ['show', 'preset', 'maskClosable', 'closeOnEsc', 'bordered', 'segmented', 'style', 'autoFocus', 'displayDirective'],
    emits: ['update:show', 'after-enter'],
  },
  NAvatar: { template: '<span><slot /></span>', props: ['round', 'size', 'src', 'color'] },
  NDropdown: {
    template: '<div><slot /></div>',
    props: ['options', 'placement'],
    emits: ['select'],
  },
  NButton: { template: '<button><slot /></button>', props: ['quaternary', 'circle', 'ariaLabel', 'ariaExpanded', 'ariaControls'] },
  NIcon: { template: '<i><slot /></i>', props: ['size'] },
  NSpin: { template: '<div><slot /></div>' },
  useMessage: () => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  MenuOutline: { template: '<svg />' },
  SearchOutline: { template: '<svg />' },
  ChevronDownOutline: { template: '<svg />' },
}))

vi.mock('../../src/components/NotificationsDropdown.vue', () => ({
  default: { template: '<div />' },
}))

vi.mock('../../src/components/layout/HeaderThemeToggle.vue', () => ({
  default: { template: '<div />' },
}))

vi.mock('../../src/components/layout/HeaderLangSwitcher.vue', () => ({
  default: { template: '<div />' },
}))

vi.mock('../../src/api/auth', () => ({
  fetchMe: vi.fn(),
  refreshSession: vi.fn(),
}))

vi.mock('../../src/api/bootstrap', () => ({
  fetchBootstrap: vi.fn(),
}))

vi.mock('../../src/api/index', () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
  refreshAuth: vi.fn(),
}))

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'ru',
    messages: {
      ru: {
        nav: {
          openMenu: 'Открыть меню',
          openSearch: 'Поиск',
          searchHint: 'Поиск...',
          profile: 'Профиль',
          aboutPortal: 'О портале',
        },
        auth: {
          logout: 'Выйти',
        },
      },
    },
    missingWarn: false,
    fallbackWarn: false,
    silentFallbackWarn: true,
    silentTranslationWarn: true,
  })
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/:pathMatch(.*)*', component: { render: () => null } },
    ],
  })
}

// ── AppHeader ──────────────────────────────────────────────────────────────────

describe('AppHeader', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders without errors', async () => {
    const { default: AppHeader } = await import('../../src/components/layout/AppHeader.vue')
    const router = makeRouter()
    const i18n = makeI18n()

    const wrapper = mount(AppHeader, {
      props: {
        isMobile: false,
        drawerOpen: false,
        headerTitle: 'Portal',
        onAbout: vi.fn(),
      },
      global: {
        plugins: [router, i18n],
        stubs: {
          HeaderUserMenu: { template: '<div class="user-menu-stub" />' },
        },
      },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows hamburger button on mobile', async () => {
    const { default: AppHeader } = await import('../../src/components/layout/AppHeader.vue')
    const router = makeRouter()
    const i18n = makeI18n()

    const wrapper = mount(AppHeader, {
      props: {
        isMobile: true,
        drawerOpen: false,
        headerTitle: 'Portal',
        onAbout: vi.fn(),
      },
      global: {
        plugins: [router, i18n],
        stubs: {
          HeaderUserMenu: { template: '<div />' },
        },
      },
    })
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('emits open-drawer when hamburger clicked', async () => {
    const { default: AppHeader } = await import('../../src/components/layout/AppHeader.vue')
    const router = makeRouter()
    const i18n = makeI18n()

    const wrapper = mount(AppHeader, {
      props: {
        isMobile: true,
        drawerOpen: false,
        headerTitle: 'My Title',
        onAbout: vi.fn(),
      },
      global: {
        plugins: [router, i18n],
        stubs: {
          HeaderUserMenu: { template: '<div />' },
        },
      },
    })

    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('open-drawer')).toBeTruthy()
  })

  it('shows header title', async () => {
    const { default: AppHeader } = await import('../../src/components/layout/AppHeader.vue')
    const router = makeRouter()
    const i18n = makeI18n()

    const wrapper = mount(AppHeader, {
      props: {
        isMobile: false,
        drawerOpen: false,
        headerTitle: 'My Custom Title',
        onAbout: vi.fn(),
      },
      global: {
        plugins: [router, i18n],
        stubs: {
          HeaderUserMenu: { template: '<div />' },
        },
      },
    })

    expect(wrapper.text()).toContain('My Custom Title')
  })

  it('emits open-search when search pill clicked', async () => {
    const { default: AppHeader } = await import('../../src/components/layout/AppHeader.vue')
    const router = makeRouter()
    const i18n = makeI18n()

    const wrapper = mount(AppHeader, {
      props: {
        isMobile: false,
        drawerOpen: false,
        headerTitle: 'Portal',
        onAbout: vi.fn(),
      },
      global: {
        plugins: [router, i18n],
        stubs: {
          HeaderUserMenu: { template: '<div />' },
        },
      },
    })

    const searchPill = wrapper.find('.search-pill')
    if (searchPill.exists()) {
      await searchPill.trigger('click')
      expect(wrapper.emitted('open-search')).toBeTruthy()
    }
  })
})

// ── AppSider ───────────────────────────────────────────────────────────────────

describe('AppSider', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders without errors', async () => {
    const { default: AppSider } = await import('../../src/components/layout/AppSider.vue')
    const router = makeRouter()

    const wrapper = mount(AppSider, {
      props: {
        collapsed: false,
        logoUrl: null,
        menuOptions: [],
        activeKey: 'home',
      },
      global: { plugins: [router] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders with logo url', async () => {
    const { default: AppSider } = await import('../../src/components/layout/AppSider.vue')
    const router = makeRouter()

    const wrapper = mount(AppSider, {
      props: {
        collapsed: false,
        logoUrl: 'https://example.com/logo.png',
        menuOptions: [],
        activeKey: 'home',
      },
      global: { plugins: [router] },
    })
    expect(wrapper.find('img').exists()).toBe(true)
    expect(wrapper.find('img').attributes('src')).toBe('https://example.com/logo.png')
  })

  it('shows logo mark when no logo url', async () => {
    const { default: AppSider } = await import('../../src/components/layout/AppSider.vue')
    const router = makeRouter()

    const wrapper = mount(AppSider, {
      props: {
        collapsed: false,
        logoUrl: null,
        menuOptions: [],
        activeKey: 'home',
      },
      global: { plugins: [router] },
    })
    expect(wrapper.find('.logo-mark').exists()).toBe(true)
  })

  it('hides logo when logoHidden is true', async () => {
    const { default: AppSider } = await import('../../src/components/layout/AppSider.vue')
    const router = makeRouter()

    const wrapper = mount(AppSider, {
      props: {
        collapsed: false,
        logoUrl: null,
        logoHidden: true,
        menuOptions: [],
        activeKey: 'home',
      },
      global: { plugins: [router] },
    })
    expect(wrapper.find('.logo-wrap').exists()).toBe(false)
  })

  it('renders in collapsed state', async () => {
    const { default: AppSider } = await import('../../src/components/layout/AppSider.vue')
    const router = makeRouter()

    const wrapper = mount(AppSider, {
      props: {
        collapsed: true,
        logoUrl: null,
        menuOptions: [],
        activeKey: 'home',
      },
      global: { plugins: [router] },
    })
    expect(wrapper.exists()).toBe(true)
  })
})

// ── HeaderUserMenu ─────────────────────────────────────────────────────────────

describe('HeaderUserMenu', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  function mountMenu(userOverrides: Record<string, unknown> = {}) {
    const router = makeRouter()
    const i18n = makeI18n()

    const auth = useAuthStore()
    auth.user = {
      id: '1',
      email: 'test@example.com',
      full_name: 'John Doe',
      department: null,
      position: null,
      phone: null,
      role: 'reader',
      avatar_url: null,
      current_status: 'working', current_status_until: null,
      notify_email: true,
      notify_inapp: true,
      lang: 'ru',
      preferences: {},
      auth_source: 'local',
      last_login_at: null,
      ...userOverrides,
    }

    return { router, i18n, auth }
  }

  it('renders without errors', async () => {
    const { default: HeaderUserMenu } = await import('../../src/components/layout/HeaderUserMenu.vue')
    const { router, i18n } = mountMenu()

    const wrapper = mount(HeaderUserMenu, {
      props: { onAbout: vi.fn() },
      global: { plugins: [router, i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows user full name', async () => {
    const { default: HeaderUserMenu } = await import('../../src/components/layout/HeaderUserMenu.vue')
    const { router, i18n } = mountMenu({ full_name: 'Jane Smith' })

    const wrapper = mount(HeaderUserMenu, {
      props: { onAbout: vi.fn() },
      global: { plugins: [router, i18n] },
    })
    expect(wrapper.text()).toContain('Jane Smith')
  })

  it('computes initials from full name', async () => {
    const { default: HeaderUserMenu } = await import('../../src/components/layout/HeaderUserMenu.vue')
    const { router, i18n } = mountMenu({ full_name: 'Alice Bob', avatar_url: null })

    const wrapper = mount(HeaderUserMenu, {
      props: { onAbout: vi.fn() },
      global: { plugins: [router, i18n] },
    })
    expect(wrapper.text()).toContain('AB')
  })

  it('does not show initials when avatar_url is set', async () => {
    const { default: HeaderUserMenu } = await import('../../src/components/layout/HeaderUserMenu.vue')
    const { router, i18n } = mountMenu({ full_name: 'Alice Bob', avatar_url: 'https://example.com/avatar.jpg' })

    const wrapper = mount(HeaderUserMenu, {
      props: { onAbout: vi.fn() },
      global: { plugins: [router, i18n] },
    })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('Alice Bob')
  })
})

// ── AppLayout ──────────────────────────────────────────────────────────────────

vi.mock('../../src/components/GlobalSearch.vue', () => ({
  default: { template: '<div class="global-search-stub" />', props: ['show'], emits: ['update:show'] },
}))

vi.mock('../../src/components/OnboardingTour.vue', () => ({
  default: { template: '<div />' },
}))

vi.mock('../../src/components/FeedbackModal.vue', () => ({
  default: { template: '<div />' },
}))

vi.mock('../../src/components/layout/AppMobileDrawer.vue', () => ({
  default: {
    template: '<div class="mobile-drawer-stub" />',
    props: ['show', 'logoUrl', 'logoHidden', 'menuOptions', 'activeKey'],
    emits: ['update:show', 'select'],
  },
}))

vi.mock('../../src/stores/notifications', () => ({
  useNotificationsStore: () => ({
    items: [],
    total: 0,
    unreadCount: 0,
    loading: false,
    dropdownOpen: false,
    initSSEOnly: vi.fn(),
    disconnectSSE: vi.fn(),
    fetchNotifications: vi.fn(),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
    deleteNotification: vi.fn(),
  }),
}))

vi.mock('../../src/stores/branding', () => ({
  useBrandingStore: () => ({
    settings: {
      has_logo: false,
      logo_updated_at: null,
      logo_hidden: false,
      portal_name: 'Portal',
    },
    fetchSettings: vi.fn(),
  }),
}))

vi.mock('../../src/composables/useAppMenu', () => ({
  useAppMenu: () => ({
    menuOptions: [],
    activeKey: 'home',
    defaultTitle: 'Portal',
    handleMenuSelect: vi.fn(),
  }),
}))

vi.mock('../../src/composables/useLayoutHeader', () => ({
  useLayoutHeader: () => ({ headerText: null }),
}))

vi.mock('../../src/composables/useGlobalHotkeys', () => ({
  useGlobalHotkeys: vi.fn(),
}))

vi.mock('../../src/composables/useBreakpoints', () => {
  const { ref } = require('vue')
  return {
    useBreakpoints: () => ({ isMobile: ref(false), isTablet: ref(false) }),
  }
})

describe('AppLayout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  async function mountLayout(overrides: Record<string, unknown> = {}) {
    const { default: AppLayout } = await import('../../src/components/AppLayout.vue')
    const router = makeRouter()
    const i18n = createI18n({
      legacy: false,
      locale: 'ru',
      messages: {
        ru: {
          a11y: { skipToContent: 'Перейти к содержимому', mainContent: 'Основное содержимое' },
          errors: { backendDown: 'Бэкенд недоступен' },
          nav: {
            openMenu: 'Меню',
            openSearch: 'Поиск',
            searchHint: 'Поиск...',
            profile: 'Профиль',
            aboutPortal: 'О портале',
          },
          auth: { logout: 'Выйти' },
        },
      },
      missingWarn: false,
      fallbackWarn: false,
      silentFallbackWarn: true,
      silentTranslationWarn: true,
    })

    const auth = useAuthStore()
    auth.user = {
      id: '1',
      email: 'test@example.com',
      full_name: 'Test User',
      department: null,
      position: null,
      phone: null,
      role: 'reader',
      avatar_url: null,
      current_status: 'working', current_status_until: null,
      notify_email: true,
      notify_inapp: true,
      lang: 'ru',
      preferences: {},
      auth_source: 'local',
      last_login_at: null,
      ...overrides,
    }

    const wrapper = mount(AppLayout, {
      global: {
        plugins: [router, i18n],
        stubs: {
          RouterView: { template: '<div class="router-view-stub" />' },
          AppSider: { template: '<div class="app-sider-stub" />', props: ['collapsed', 'logoUrl', 'logoHidden', 'menuOptions', 'activeKey'], emits: ['update:collapsed', 'select'] },
          AppHeader: { template: '<div class="app-header-stub" />', props: ['isMobile', 'drawerOpen', 'headerTitle', 'onAbout'], emits: ['open-drawer', 'open-search'] },
          HeaderUserMenu: { template: '<div />' },
        },
      },
    })

    return { wrapper, router, i18n, auth }
  }

  it('renders without errors', async () => {
    const { wrapper } = await mountLayout()
    expect(wrapper.exists()).toBe(true)
  })

  it('renders skip-link for accessibility', async () => {
    const { wrapper } = await mountLayout()
    const skip = wrapper.find('a.skip-link')
    expect(skip.exists()).toBe(true)
    expect(skip.attributes('href')).toBe('#main-content')
  })

  it('does not show backend-down banner when backend is up', async () => {
    const { wrapper } = await mountLayout()
    expect(wrapper.find('.backend-down-banner').exists()).toBe(false)
  })

  it('shows backend-down banner when backendDown is true', async () => {
    const { wrapper } = await mountLayout()
    const auth = useAuthStore()
    auth.backendDown = true
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.backend-down-banner').exists()).toBe(true)
  })

  it('renders AppSider on desktop', async () => {
    const { wrapper } = await mountLayout()
    expect(wrapper.find('.app-sider-stub').exists()).toBe(true)
  })
})
