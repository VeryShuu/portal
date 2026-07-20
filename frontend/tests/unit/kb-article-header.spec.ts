import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'text', 'disabled', 'loading', 'quaternary', 'circle', 'title', 'ghost', 'attrType'],
    emits: ['click'],
  },
  NDropdown: {
    template: '<div class="n-dropdown"><slot /></div>',
    props: ['options', 'trigger'],
    emits: ['select'],
  },
}))

const MOCK_ARTICLE = {
  id: '00000000-0000-0000-0000-000000000001',
  title: 'Test Article',
  status: 'published' as const,
  user_permission: 'viewer' as const,
  view_count: 42,
  version: 3,
  tags: [{ id: 'tag1', name: 'typescript' }],
  updated_at: '2024-01-15T00:00:00Z',
  created_by: { id: 'u1', full_name: 'Автор Тестов' },
}

describe('KbArticleHeader.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows article title', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Test Article')
  })

  it('shows published status', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.article-status--published').exists()).toBe(true)
  })

  it('shows draft status', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const draft = { ...MOCK_ARTICLE, status: 'draft' as const }
    const wrapper = mount(KbArticleHeader, {
      props: { article: draft as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.article-status--draft').exists()).toBe(true)
  })

  it('shows tags', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('typescript')
  })

  it('shows edit button for editor permission', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const editorArticle = { ...MOCK_ARTICLE, user_permission: 'editor' as const }
    const wrapper = mount(KbArticleHeader, {
      props: { article: editorArticle as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.article-actions').exists()).toBe(true)
  })

  it('shows author name in meta', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('Автор Тестов')
  })

  it('shows view count in meta', async () => {
    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('42')
  })

  it('shows delete button for admin', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.user = { id: 'u2', role: 'admin' } as any

    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    const deleteBtn = wrapper.findAll('button').filter(b => b.text().includes('common.delete'))
    expect(deleteBtn.length).toBe(1)
  })

  it('shows delete button for creator', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.user = { id: 'u1', role: 'editor' } as any

    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    const deleteBtn = wrapper.findAll('button').filter(b => b.text().includes('common.delete'))
    expect(deleteBtn.length).toBe(1)
  })

  it('hides delete button for non-creator non-admin', async () => {
    const { useAuthStore } = await import('../../src/stores/auth')
    const auth = useAuthStore()
    auth.user = { id: 'u2', role: 'editor' } as any

    const KbArticleHeader = (await import('../../src/components/KbArticleHeader.vue')).default
    const wrapper = mount(KbArticleHeader, {
      props: { article: MOCK_ARTICLE as any },
      global: { plugins: [i18n] },
    })
    const deleteBtn = wrapper.findAll('button').filter(b => b.text().includes('common.delete'))
    expect(deleteBtn.length).toBe(0)
  })
})
