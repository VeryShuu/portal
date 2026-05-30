/**
 * Smoke-тест NewsPollPanel.vue: монтируется при пустом / существующем poll.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'ghost', 'loading', 'disabled', 'dashed', 'quaternary'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  NFormItem: { template: '<div class="n-form-item"><slot /></div>', props: ['label'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type'],
    emits: ['update:value'],
  },
  NSelect: {
    template: '<select />',
    props: ['value', 'options', 'disabled'],
    emits: ['update:value'],
  },
  NCheckbox: {
    template: '<input type="checkbox" />',
    props: ['checked', 'disabled'],
    emits: ['update:checked'],
  },
  NInputNumber: { template: '<input type="number" />', props: ['value'] },
  NDatePicker: { template: '<input type="date" />', props: ['value', 'type', 'clearable'] },
  NUpload: {
    template: '<div class="n-upload"><slot /></div>',
    props: ['customRequest', 'showFileList', 'accept'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => ({
  AddOutline: { template: '<span />' },
  CloseOutline: { template: '<span />' },
  ArrowUpOutline: { template: '<span />' },
  ArrowDownOutline: { template: '<span />' },
  CloudUploadOutline: { template: '<span />' },
}))

vi.mock('../../src/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

const pollData = ref<unknown>(null)

vi.mock('../../src/queries/news', () => ({
  useNewsPollQuery: vi.fn(() => ({ data: pollData })),
  useCreateNewsPollMutation: vi.fn(() => ({ mutateAsync: vi.fn() })),
  useUpdateNewsPollMutation: vi.fn(() => ({ mutateAsync: vi.fn() })),
  useDeleteNewsPollMutation: vi.fn(() => ({ mutateAsync: vi.fn() })),
}))

vi.mock('../../src/api/news', () => ({
  uploadNewsInlineMedia: vi.fn(),
}))

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'error'),
}))

describe('NewsPollPanel.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    pollData.value = null
  })

  it('mounts without newsId and shows hint', async () => {
    const { default: NewsPollPanel } = await import('../../src/components/news/poll-panel/NewsPollPanel.vue')
    const wrapper = mount(NewsPollPanel, {
      props: {},
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.u-panel__hint').exists()).toBe(true)
  })

  it('shows create button when newsId present and no poll', async () => {
    const { default: NewsPollPanel } = await import('../../src/components/news/poll-panel/NewsPollPanel.vue')
    const wrapper = mount(NewsPollPanel, {
      props: { newsId: '550e8400-e29b-41d4-a716-446655440000', hasPoll: false },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.poll-empty-state').exists()).toBe(true)
  })

  it('mounts when poll data is provided', async () => {
    pollData.value = {
      id: 'p1',
      is_anonymous: true,
      allow_revote: false,
      results_visibility: 'always',
      closes_at: null,
      questions: [],
      total_voters: 0,
    }
    const { default: NewsPollPanel } = await import('../../src/components/news/poll-panel/NewsPollPanel.vue')
    const wrapper = mount(NewsPollPanel, {
      props: { newsId: '550e8400-e29b-41d4-a716-446655440000', hasPoll: true },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })
})
