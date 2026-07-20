import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'text', 'disabled', 'loading', 'quaternary', 'circle', 'title'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  LinkOutline: { template: '<span />' },
  ShieldCheckmarkOutline: { template: '<span />' },
  OpenOutline: { template: '<span />' },
  ArrowForwardOutline: { template: '<span />' },
  CreateOutline: { template: '<span />' },
  TrashOutline: { template: '<span />' },
  ReorderTwoOutline: { template: '<span />' },
  BookOutline: { template: '<span />' },
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('../../src/api/links', () => ({
  recordLinkClick: vi.fn(),
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
