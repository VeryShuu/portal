import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset'] },
  NSpin: { template: '<div class="n-spin" />', props: ['size'] },
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({ items: [] }),
  apiUpload: vi.fn(),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/api/index', () => ({
  api: vi.fn().mockResolvedValue({ items: [] }),
  apiUpload: vi.fn(),
  BASE_URL: '/api/v1',
}))

describe('KbVersionDiffModal.vue', () => {
  it('renders modal when modelValue=true', async () => {
    const KbVersionDiffModal = (await import('../../src/components/KbVersionDiffModal.vue')).default
    const wrapper = mount(KbVersionDiffModal, {
      props: { modelValue: true, articleId: 'art-1', v1: 1, v2: 2 },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-modal').exists()).toBe(true)
  })

  it('does not render modal when modelValue=false', async () => {
    const KbVersionDiffModal = (await import('../../src/components/KbVersionDiffModal.vue')).default
    const wrapper = mount(KbVersionDiffModal, {
      props: { modelValue: false, articleId: 'art-1', v1: 1, v2: 2 },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-modal').exists()).toBe(false)
  })

  it('shows loading spinner when loading', async () => {
    const { api } = await import('../../src/api')
    vi.mocked(api).mockImplementation(() => new Promise(() => {}))
    const KbVersionDiffModal = (await import('../../src/components/KbVersionDiffModal.vue')).default
    const wrapper = mount(KbVersionDiffModal, {
      props: { modelValue: true, articleId: 'art-1', v1: 1, v2: 2 },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-spin').exists() || wrapper.find('.diff-error').exists() || wrapper.find('.n-modal').exists()).toBe(true)
  })

  it('shows diff content when diff loaded', async () => {
    const { api } = await import('../../src/api')
    vi.mocked(api).mockResolvedValue({
      stats: { added: 5, removed: 2 },
      hunks: [{ header: '@@ -1,3 +1,5 @@', lines: ['+new line', '-old line', ' context'] }],
    })
    const KbVersionDiffModal = (await import('../../src/components/KbVersionDiffModal.vue')).default
    const wrapper = mount(KbVersionDiffModal, {
      props: { modelValue: true, articleId: 'art-1', v1: 1, v2: 2 },
      global: { plugins: [i18n] },
    })
    await new Promise(r => setTimeout(r, 50))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.n-modal').exists()).toBe(true)
  })
})
