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
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type', 'rows'],
    emits: ['update:value'],
  },
}))

vi.mock('../../src/composables/useKbArticleComments', () => ({
  useKbArticleComments: vi.fn(() => ({
    comments: { value: [] },
    total: { value: 0 },
    submitting: { value: false },
    newComment: { value: '' },
    submit: vi.fn(),
    remove: vi.fn(),
  })),
}))

describe('KbArticleCommentsTab.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const KbArticleCommentsTab = (await import('../../src/components/KbArticleCommentsTab.vue')).default
    const wrapper = mount(KbArticleCommentsTab, {
      props: { articleId: 'art-1' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows empty state when no comments', async () => {
    const KbArticleCommentsTab = (await import('../../src/components/KbArticleCommentsTab.vue')).default
    const wrapper = mount(KbArticleCommentsTab, {
      props: { articleId: 'art-1' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.comment-form').exists()).toBe(true)
  })
})
