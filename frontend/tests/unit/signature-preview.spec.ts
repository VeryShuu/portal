import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru: {}, en: {} },
})

import SignaturePreview from '../../src/components/signature/SignaturePreview.vue'

function mountPreview(html = '') {
  return mount(SignaturePreview, {
    global: { plugins: [i18n] },
    props: { html },
  })
}

describe('SignaturePreview.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the empty placeholder when html prop is empty', () => {
    const wrapper = mountPreview('')

    expect(wrapper.find('.signature-preview__empty').exists()).toBe(true)
    expect(wrapper.find('.signature-preview__empty').text()).toContain('signature.preview.empty')
    expect(wrapper.find('iframe').exists()).toBe(false)
  })

  it('renders the iframe with srcdoc when html prop is set', async () => {
    const wrapper = mountPreview('<p>signature body</p>')

    const frame = wrapper.find('iframe')
    expect(frame.exists()).toBe(true)
    expect(frame.attributes('srcdoc')).toBe('<p>signature body</p>')
    // watch + nextTick triggers resize(); we just verify it doesn't throw.
    await flushPromises()
  })

  it('resize() early-returns when frame/contentDocument is missing', async () => {
    const wrapper = mountPreview('<p>x</p>')
    const frame = wrapper.find('iframe')
    // No contentDocument body in jsdom -> guard path taken.
    await frame.trigger('load')
    await flushPromises()

    // Height should remain unset.
    const el = frame.element as HTMLIFrameElement
    expect(el.style.height).toBe('')
  })

  it('resize() sets frame height to scrollHeight when body is available', async () => {
    const wrapper = mountPreview('<p>body</p>')
    const frame = wrapper.find('iframe')
    const el = frame.element as HTMLIFrameElement

    // Simulate a content document with a body that reports scrollHeight.
    Object.defineProperty(el, 'contentDocument', {
      configurable: true,
      value: { body: { scrollHeight: 250 } },
    })

    await frame.trigger('load')
    await flushPromises()

    expect(el.style.height).toBe('250px')
  })
})
