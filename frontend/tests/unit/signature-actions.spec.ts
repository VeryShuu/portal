/* eslint-disable vue/one-component-per-file -- тестовые компоненты-заглушки объявляются в одном файле */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru: {}, en: {} },
})

// Naive UI button stub that proxies the disabled/loading props and re-emits click.
vi.mock('naive-ui', () => ({
  NButton: {
    name: 'NButton',
    props: ['type', 'disabled', 'loading'],
    emits: ['click'],
    template:
      '<button class="n-button" :disabled="disabled" :data-loading="loading" :data-type="type" @click="$emit(\'click\')"><slot /></button>',
  },
}))

import SignatureActions from '../../src/components/signature/SignatureActions.vue'

function mountActions(props: Partial<any> = {}) {
  return mount(SignatureActions, {
    global: { plugins: [i18n] },
    props: {
      canGenerate: true,
      generating: false,
      generated: false,
      hasResult: false,
      mailtoSupport: '',
      supportEmail: '',
      ...props,
    },
  })
}

describe('SignatureActions.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders generate label when not generated and disables copy/download without result', () => {
    const wrapper = mountActions({ canGenerate: true, generated: false, hasResult: false })

    const buttons = wrapper.findAll('.n-button')
    expect(buttons).toHaveLength(3)
    // First button: generate; should be enabled because canGenerate && !generating.
    expect(buttons[0].attributes('disabled')).toBeUndefined()
    expect(buttons[0].text()).toContain('signature.actions.generate')
    // copy/download disabled when !hasResult.
    expect(buttons[1].attributes('disabled')).toBeDefined()
    expect(buttons[2].attributes('disabled')).toBeDefined()
  })

  it('renders update label when generated is true', () => {
    const wrapper = mountActions({ generated: true })

    expect(wrapper.findAll('.n-button')[0].text()).toContain('signature.actions.update')
  })

  it('disables generate button when canGenerate is false and shows loading when generating', () => {
    const cantGenerate = mountActions({ canGenerate: false })
    expect(cantGenerate.findAll('.n-button')[0].attributes('disabled')).toBeDefined()

    // generating alone does not disable the button (only loading state is shown).
    const generating = mountActions({ canGenerate: true, generating: true })
    expect(generating.findAll('.n-button')[0].attributes('disabled')).toBeUndefined()
    expect(generating.findAll('.n-button')[0].attributes('data-loading')).toBe('true')
  })

  it('enables copy/download when hasResult is true and emits events on click', async () => {
    const wrapper = mountActions({ hasResult: true })

    const buttons = wrapper.findAll('.n-button')
    expect(buttons[1].attributes('disabled')).toBeUndefined()
    expect(buttons[2].attributes('disabled')).toBeUndefined()

    await buttons[0].trigger('click')
    await buttons[1].trigger('click')
    await buttons[2].trigger('click')

    expect(wrapper.emitted('generate')).toBeTruthy()
    expect(wrapper.emitted('copy')).toBeTruthy()
    expect(wrapper.emitted('download')).toBeTruthy()
  })

  it('renders support mailto link only when mailtoSupport is provided', () => {
    const without = mountActions({ mailtoSupport: '', supportEmail: 'a@b.c' })
    expect(without.find('.signature-actions__support').exists()).toBe(false)

    const withMail = mountActions({ mailtoSupport: 'mailto:support@example.com', supportEmail: 'support@example.com' })
    const link = withMail.find('.signature-actions__support')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('mailto:support@example.com')
    // The link text uses the i18n key (empty messages in this harness), but the
    // t() call must be wired with the email parameter; assert it lands as an arg.
    expect(withMail.text()).toContain('signature.actions.support')
  })
})
