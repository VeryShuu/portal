/**
 * Unit-тест ParticipantPicker.vue: единое поле поиска.
 * Сотрудник ищется в каталоге; если введён email и сотрудник не найден —
 * в выпадающем списке появляется опция «внешний участник».
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { NSelect } from 'naive-ui'
import type { InvitedUser } from '../../src/api/meetings'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru: {}, en: {} },
})

vi.mock('naive-ui', () => ({
  NSelect: {
    name: 'NSelect',
    template: '<div class="n-select" />',
    props: ['value', 'options', 'loading', 'placeholder', 'multiple', 'filterable', 'remote', 'clearFilterAfterSelect', 'renderLabel'],
    emits: ['search', 'update:value'],
  },
  NButton: {
    name: 'NButton',
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['size', 'tertiary', 'type', 'disabled', 'loading'],
    emits: ['click'],
  },
}))

const searchParticipants = vi.fn<(q: string) => Promise<InvitedUser[]>>()
vi.mock('../../src/api/meetings', () => ({
  searchParticipants: (q: string) => searchParticipants(q),
}))

// Модал массового ввода тестируется собственной логикой; здесь проверяем только
// интеграцию с пикером (кнопка → открытие → прокидывание add наверх).
const pasteModalAdd = vi.fn()
vi.mock('../../src/components/meetings/PasteParticipantsModal.vue', () => ({
  default: {
    name: 'PasteParticipantsModal',
    template: '<div class="paste-modal-stub" />',
    props: ['show', 'existingEmails'],
    emits: ['update:show', 'add'],
    mounted() {
      pasteModalAdd.mockImplementation((items: InvitedUser[]) => this.$emit('add', items))
    },
  },
}))

import ParticipantPicker from '../../src/components/meetings/ParticipantPicker.vue'

function mountPicker(modelValue: InvitedUser[] = []) {
  return mount(ParticipantPicker, {
    props: { modelValue, minChars: 3 },
    global: { plugins: [i18n] },
  })
}

function optionValues(wrapper: ReturnType<typeof mountPicker>): string[] {
  const opts = wrapper.findComponent(NSelect).props('options') as Array<{ value: string }>
  return opts.map(o => o.value)
}

describe('ParticipantPicker single-field external contacts', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    searchParticipants.mockResolvedValue([])
  })

  it('offers an external option when a valid email has no employee match', async () => {
    const wrapper = mountPicker([])
    await wrapper.findComponent(NSelect).vm.$emit('search', 'Guest@Partner.com')

    expect(optionValues(wrapper)).toContain('ext:guest@partner.com')
  })

  it('emits an external InvitedUser when the external option is selected', async () => {
    const wrapper = mountPicker([])
    const select = wrapper.findComponent(NSelect)
    await select.vm.$emit('search', 'guest@partner.com')
    await select.vm.$emit('update:value', ['ext:guest@partner.com'])

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect((emitted![0][0] as InvitedUser[])[0]).toEqual({
      user_id: 'ext:guest@partner.com',
      full_name: 'guest@partner.com',
      email: 'guest@partner.com',
      source: 'external',
    })
  })

  it('does not offer an external option for an invalid email', async () => {
    const wrapper = mountPicker([])
    await wrapper.findComponent(NSelect).vm.$emit('search', 'not-an-email')

    expect(optionValues(wrapper).some(v => v.startsWith('ext:'))).toBe(false)
  })

  it('does not offer an external option for an already-added email', async () => {
    const wrapper = mountPicker([
      { user_id: 'ext:dup@partner.com', full_name: 'dup@partner.com', email: 'dup@partner.com', source: 'external' },
    ])
    await wrapper.findComponent(NSelect).vm.$emit('search', 'DUP@partner.com')

    expect(optionValues(wrapper)).not.toContain('ext:dup@partner.com')
  })

  it('renders an external badge for external participants', () => {
    const wrapper = mountPicker([
      { user_id: 'ext:x@partner.com', full_name: 'x@partner.com', email: 'x@partner.com', source: 'external' },
    ])
    expect(wrapper.find('.participant-tag__badge').exists()).toBe(true)
  })
})

describe('ParticipantPicker bulk paste integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('opens the paste modal when the paste button is clicked', async () => {
    const wrapper = mountPicker([])
    const btn = wrapper.find('.paste-list-btn')
    expect(btn.exists()).toBe(true)

    await btn.trigger('click')
    expect(wrapper.findComponent({ name: 'PasteParticipantsModal' }).props('show')).toBe(true)
  })

  it('emits update:modelValue with resolved participants on modal add', async () => {
    const wrapper = mountPicker([])
    const modal = wrapper.findComponent({ name: 'PasteParticipantsModal' })

    const added: InvitedUser[] = [
      { user_id: 'kc-1', full_name: 'Иван', email: 'ivan@company.com', source: 'keycloak' },
      { user_id: 'ext:ext@partner.com', full_name: 'ext@partner.com', email: 'ext@partner.com', source: 'external' },
    ]
    await modal.vm.$emit('add', added)

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0] as InvitedUser[]).toEqual(added)
  })

  it('deduplicates bulk-added participants by email against existing', async () => {
    const existing: InvitedUser = {
      user_id: 'kc-1',
      full_name: 'Иван',
      email: 'ivan@company.com',
      source: 'keycloak',
    }
    const wrapper = mountPicker([existing])
    const modal = wrapper.findComponent({ name: 'PasteParticipantsModal' })

    // Тот же email уже приглашён → должен отфильтроваться.
    await modal.vm.$emit('add', [
      existing,
      { user_id: 'kc-2', full_name: 'Пётр', email: 'petr@company.com', source: 'keycloak' },
    ])

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    const result = emitted![0][0] as InvitedUser[]
    expect(result).toHaveLength(2)
    expect(result.map(u => u.email)).toEqual(['ivan@company.com', 'petr@company.com'])
  })
})
