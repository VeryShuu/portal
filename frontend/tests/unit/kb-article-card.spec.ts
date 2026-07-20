import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

describe('KbArticleCard.vue', () => {
  const MOCK_ARTICLE = {
    id: 'art-1',
    title: 'Test Article',
    status: 'published',
    view_count: 10,
    tags: [{ id: 't1', name: 'Vue', slug: 'vue' }],
    section: { id: 's1', title: 'Frontend' },
    updated_at: '2024-01-15T00:00:00Z',
  }

  it('renders article title', async () => {
    const { default: KbArticleCard } = await import('../../src/components/KbArticleCard.vue')
    const wrapper = mount(KbArticleCard, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('Test Article')
  })

  it('emits open event on click', async () => {
    const { default: KbArticleCard } = await import('../../src/components/KbArticleCard.vue')
    const wrapper = mount(KbArticleCard, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    await wrapper.find('.kb-card').trigger('click')
    expect(wrapper.emitted('open')).toBeTruthy()
  })

  it('shows tags from article', async () => {
    const { default: KbArticleCard } = await import('../../src/components/KbArticleCard.vue')
    const wrapper = mount(KbArticleCard, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Vue')
  })

  it('marks active tag', async () => {
    const { default: KbArticleCard } = await import('../../src/components/KbArticleCard.vue')
    const wrapper = mount(KbArticleCard, {
      props: { article: MOCK_ARTICLE as any, activeTag: 'vue' },
      global: { plugins: [i18n] },
    })
    const tag = wrapper.find('.kb-tag--active')
    expect(tag.exists()).toBe(true)
  })
})
