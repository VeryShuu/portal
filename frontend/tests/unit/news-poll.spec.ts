/**
 * Smoke-тест NewsPoll.vue: монтируется без ошибок при разных состояниях poll.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'round', 'bordered'] },
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'ghost', 'loading', 'disabled', 'block'],
    emits: ['click'],
  },
  NSpace: { template: '<div class="n-space"><slot /></div>' },
  NSpin: { template: '<div class="n-spin" />', props: ['show'] },
  NModal: { template: '<div class="n-modal"><slot /></div>', props: ['show', 'preset', 'title', 'bordered', 'size'] },
  NEmpty: { template: '<div class="n-empty" />', props: ['description'] },
  NInput: { template: '<input />', props: ['value', 'placeholder', 'type'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn() })),
  useRoute: vi.fn(() => ({ query: {}, params: {} })),
}))

vi.mock('@vicons/ionicons5', () => ({
  BarChartOutline: { template: '<span />' },
  AddOutline: { template: '<span />' },
  CloseOutline: { template: '<span />' },
}))

const pollData = ref<unknown>(null)

vi.mock('../../src/queries/news', () => ({
  useNewsPollQuery: vi.fn(() => ({ data: pollData, isLoading: ref(false) })),
  useNewsPollVotersQuery: vi.fn(() => ({ data: ref(null), isLoading: ref(false) })),
  useVoteNewsPollMutation: vi.fn(() => ({ mutateAsync: vi.fn() })),
  useRevokeNewsPollVoteMutation: vi.fn(() => ({ mutateAsync: vi.fn() })),
  useCloseNewsPollMutation: vi.fn(() => ({ mutateAsync: vi.fn() })),
  useReopenNewsPollMutation: vi.fn(() => ({ mutateAsync: vi.fn() })),
  useDeleteNewsPollMutation: vi.fn(() => ({ mutateAsync: vi.fn() })),
}))

vi.mock('../../src/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

describe('NewsPoll.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    pollData.value = null
  })

  it('mounts without errors when poll is null', async () => {
    const { default: NewsPoll } = await import('../../src/components/news/poll/NewsPoll.vue')
    const wrapper = mount(NewsPoll, {
      props: { newsId: '550e8400-e29b-41d4-a716-446655440000' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders poll body when data is present', async () => {
    pollData.value = {
      id: 'p1',
      is_anonymous: true,
      is_closed: false,
      closes_at: null,
      can_vote: true,
      results_visibility: 'always',
      allow_revote: false,
      my_vote: null,
      questions: [
        {
          id: 'q1',
          text: 'Question 1?',
          is_required: true,
          is_multiple: false,
          max_choices: null,
          sort_order: 0,
          options: [
            { id: 'o1', text: 'Option A', image_url: null, sort_order: 0, votes_count: 0 },
            { id: 'o2', text: 'Option B', image_url: null, sort_order: 1, votes_count: 0 },
          ],
        },
      ],
    }
    const { default: NewsPoll } = await import('../../src/components/news/poll/NewsPoll.vue')
    const wrapper = mount(NewsPoll, {
      props: { newsId: '550e8400-e29b-41d4-a716-446655440000' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.news-poll').exists()).toBe(true)
    expect(wrapper.text()).toContain('Question 1?')
  })

  it('shows closed badge when poll is closed', async () => {
    pollData.value = {
      id: 'p1',
      is_anonymous: false,
      is_closed: true,
      closes_at: null,
      can_vote: false,
      results_visibility: 'always',
      allow_revote: false,
      my_vote: null,
      questions: [],
    }
    const { default: NewsPoll } = await import('../../src/components/news/poll/NewsPoll.vue')
    const wrapper = mount(NewsPoll, {
      props: { newsId: '550e8400-e29b-41d4-a716-446655440000' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.news-poll__badges').exists()).toBe(true)
  })
})
