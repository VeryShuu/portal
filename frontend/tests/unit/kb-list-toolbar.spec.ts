import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'clearable', 'size'],
    emits: ['update:value', 'input', 'update:modelValue'],
  },
  NSelect: {
    template: '<select><slot /></select>',
    props: ['value', 'options', 'placeholder', 'clearable', 'size'],
    emits: ['update:value'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  SearchOutline: { template: '<span />' },
}))

describe('KbListToolbar.vue', () => {
  it('renders without errors', async () => {
    const { default: KbListToolbar } = await import('../../src/components/KbListToolbar.vue')
    const wrapper = mount(KbListToolbar, {
      props: {
        searchQuery: '',
        statusFilter: null,
        tagFilter: null,
        tagOptions: [],
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders with search query', async () => {
    const { default: KbListToolbar } = await import('../../src/components/KbListToolbar.vue')
    const wrapper = mount(KbListToolbar, {
      props: {
        searchQuery: 'vue',
        statusFilter: 'published',
        tagFilter: null,
        tagOptions: [{ label: 'Vue', value: 'vue' }],
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
    const input = wrapper.find('input')
    expect((input.element as HTMLInputElement).value).toBe('vue')
  })
})
