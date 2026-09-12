import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset'] },
  NForm: { template: '<form @submit.prevent="$emit(\'submit\')"><slot /></form>', emits: ['submit'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'required'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type', 'rows'],
    emits: ['update:value'],
  },
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'text', 'disabled', 'loading', 'quaternary', 'circle', 'title', 'ghost', 'attrType'],
    emits: ['click'],
  },
}))

describe('KbSectionFormModal.vue', () => {
  it('renders when show=true', async () => {
    const KbSectionFormModal = (await import('../../src/components/KbSectionFormModal.vue')).default
    const wrapper = mount(KbSectionFormModal, {
      props: {
        show: true,
        form: { title: '', description: '', parent_id: null },
        saving: false,
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-modal').exists()).toBe(true)
  })

  it('hidden when show=false', async () => {
    const KbSectionFormModal = (await import('../../src/components/KbSectionFormModal.vue')).default
    const wrapper = mount(KbSectionFormModal, {
      props: {
        show: false,
        form: { title: '', description: '', parent_id: null },
        saving: false,
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-modal').exists()).toBe(false)
  })

  it('shows title value from form', async () => {
    const KbSectionFormModal = (await import('../../src/components/KbSectionFormModal.vue')).default
    const wrapper = mount(KbSectionFormModal, {
      props: {
        show: true,
        form: { title: 'My Section', description: 'desc', parent_id: null },
        saving: false,
      },
      global: { plugins: [i18n] },
    })
    const input = wrapper.find('input')
    expect(input.element.value).toBe('My Section')
  })
})
