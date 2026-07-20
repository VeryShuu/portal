import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'ru' } }),
  createI18n: () => ({ global: { t: (k: string) => k, locale: { value: 'ru' } } }),
}))

const i18n = {
  install: (app: any) => {
    app.config.globalProperties.$t = (k: string) => k
    app.config.globalProperties.$i18n = { locale: 'ru' }
  },
}

describe('KbArticleFeedback.vue', () => {
  it('renders without errors', async () => {
    const KbArticleFeedback = (await import('../../src/components/KbArticleFeedback.vue')).default
    const wrapper = mount(KbArticleFeedback, {
      props: { helpfulCount: 5, notHelpfulCount: 2, userFeedback: null },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows helpful and not helpful counts', async () => {
    const KbArticleFeedback = (await import('../../src/components/KbArticleFeedback.vue')).default
    const wrapper = mount(KbArticleFeedback, {
      props: { helpfulCount: 10, notHelpfulCount: 3, userFeedback: null },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('10')
    expect(wrapper.text()).toContain('3')
  })

  it('marks active when userFeedback is true', async () => {
    const KbArticleFeedback = (await import('../../src/components/KbArticleFeedback.vue')).default
    const wrapper = mount(KbArticleFeedback, {
      props: { helpfulCount: 5, notHelpfulCount: 2, userFeedback: true },
      global: { plugins: [i18n] },
    })
    const buttons = wrapper.findAll('.feedback-btn')
    expect(buttons[0].classes()).toContain('feedback-btn--active')
  })

  it('emits feedback event on button click', async () => {
    const KbArticleFeedback = (await import('../../src/components/KbArticleFeedback.vue')).default
    const wrapper = mount(KbArticleFeedback, {
      props: { helpfulCount: 5, notHelpfulCount: 2, userFeedback: null },
      global: { plugins: [i18n] },
    })
    await wrapper.findAll('.feedback-btn')[0].trigger('click')
    expect(wrapper.emitted('feedback')).toEqual([[true]])
  })
})
