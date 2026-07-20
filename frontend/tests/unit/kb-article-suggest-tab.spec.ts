import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

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
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('../../src/api/kb', () => ({
  suggestEdit: vi.fn(),
}))

describe('KbArticleSuggestTab.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders without errors', async () => {
    const KbArticleSuggestTab = (await import('../../src/components/KbArticleSuggestTab.vue')).default
    const wrapper = mount(KbArticleSuggestTab, {
      props: { articleId: 'art-1' },
      global: {
        plugins: [i18n],
        stubs: { RichEditor: { template: '<div class="rich-editor" />' } },
      },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('has submit button', async () => {
    const KbArticleSuggestTab = (await import('../../src/components/KbArticleSuggestTab.vue')).default
    const wrapper = mount(KbArticleSuggestTab, {
      props: { articleId: 'art-1' },
      global: {
        plugins: [i18n],
        stubs: { RichEditor: { template: '<div class="rich-editor" />' } },
      },
    })
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('has suggest-form container', async () => {
    const KbArticleSuggestTab = (await import('../../src/components/KbArticleSuggestTab.vue')).default
    const wrapper = mount(KbArticleSuggestTab, {
      props: { articleId: 'art-1' },
      global: {
        plugins: [i18n],
        stubs: { RichEditor: { template: '<div class="rich-editor" />' } },
      },
    })
    expect(wrapper.find('.suggest-form').exists()).toBe(true)
  })
})
