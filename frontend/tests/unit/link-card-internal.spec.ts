import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import LinkCard from '../../src/components/links/LinkCard.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru: {}, en: {} },
})

vi.mock('vue-router', () => ({
  RouterLink: {
    name: 'RouterLink',
    props: ['to'],
    template: '<a class="router-link" :href="to"><slot /></a>',
  },
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

vi.mock('naive-ui', () => ({
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size'] },
  NButton: { template: '<button><slot /></button>', props: ['size', 'title'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  LinkOutline: { template: '<span />' },
  ShieldCheckmarkOutline: { template: '<span />' },
  OpenOutline: { template: '<span class="icon-open" />' },
  ArrowForwardOutline: { template: '<span class="icon-internal" />' },
  CreateOutline: { template: '<span />' },
  TrashOutline: { template: '<span />' },
  ReorderTwoOutline: { template: '<span />' },
}))

vi.mock('../../src/composables/useFavicon', () => ({
  useFavicon: () => ({
    faviconFor: () => null,
    shortUrl: (u: string) => u,
    onIconError: () => {},
  }),
}))

vi.mock('../../src/api', () => ({ BASE_URL: '/api/v1' }))

function makeItem(over: Record<string, unknown>) {
  return {
    id: '1', title: 'T', description: null, iconUrl: null,
    supportsSso: false, group: '', kind: 'link', raw: {},
    ...over,
  }
}

function mountCard(item: Record<string, unknown>) {
  return mount(LinkCard, {
    props: { item: item as never, canDrag: false, isAdmin: false },
    global: { plugins: [i18n] },
  })
}

describe('LinkCard internal vs external', () => {
  it('renders internal link via router-link (same tab)', () => {
    const wrapper = mountCard(makeItem({ url: '/signature' }))
    const rl = wrapper.find('a.router-link')
    expect(rl.exists()).toBe(true)
    expect(rl.attributes('href')).toBe('/signature')
    expect(wrapper.find('.icon-internal').exists()).toBe(true)
  })

  it('renders external link as new-tab anchor', () => {
    const wrapper = mountCard(makeItem({ url: 'https://grafana.com' }))
    expect(wrapper.find('a.router-link').exists()).toBe(false)
    const a = wrapper.find('a.link-card')
    expect(a.exists()).toBe(true)
    expect(a.attributes('target')).toBe('_blank')
    expect(a.attributes('href')).toBe('https://grafana.com')
    expect(wrapper.find('.icon-open').exists()).toBe(true)
  })

  it('treats protocol-relative url as external (not internal)', () => {
    const wrapper = mountCard(makeItem({ url: '//evil.com' }))
    expect(wrapper.find('a.router-link').exists()).toBe(false)
    expect(wrapper.find('a.link-card').attributes('target')).toBe('_blank')
  })
})
