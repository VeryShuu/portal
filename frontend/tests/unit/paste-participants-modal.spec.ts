/**
 * Unit-тест PasteParticipantsModal.vue: массовый ввод ФИО/email.
 *
 * Проверяем: открытие при show=true, вызов resolveParticipants при «Распознать»,
 * отображение resolved/unresolved/ambiguous, эмит add с дедупом по existingEmails.
 *
 * Naive-UI и i18n стабаются; api-функция resolveParticipants мокается.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'ru' } }),
}))

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'loading', 'tertiary'],
    emits: ['click'],
  },
  NModal: {
    template: '<div class="n-modal" v-if="show"><slot /><slot name="footer" /></div>',
    props: ['show', 'title', 'preset', 'maskClosable'],
    emits: ['update:show'],
  },
  NInput: {
    template: '<textarea class="n-input" :value="value" :disabled="disabled" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'type', 'autosize', 'maxlength', 'showCount', 'placeholder', 'disabled'],
    emits: ['update:value'],
  },
  NSelect: {
    template: '<select class="n-select" @change="$emit(\'update:value\', $event.target.value)"><option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option></select>',
    props: ['value', 'options', 'placeholder', 'size'],
    emits: ['update:value'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

const resolveParticipants = vi.fn()
vi.mock('../../src/api/meetings', () => ({
  resolveParticipants: (...args: unknown[]) => resolveParticipants(...args),
}))

import PasteParticipantsModal from '../../src/components/meetings/PasteParticipantsModal.vue'
import type { ResolveParticipantsResponse } from '../../src/api/meetings'

const i18n = {
  install: (app: { config: { globalProperties: Record<string, unknown> } }) => {
    app.config.globalProperties.$t = (k: string) => k
    app.config.globalProperties.$i18n = { locale: 'ru' }
  },
}

function mountModal(props: Partial<{ show: boolean; existingEmails: Set<string> }> = {}) {
  return mount(PasteParticipantsModal, {
    props: {
      show: props.show ?? true,
      existingEmails: props.existingEmails ?? new Set<string>(),
    },
    global: { plugins: [i18n] },
  })
}

describe('PasteParticipantsModal.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the input stage when show=true and no result yet', () => {
    const wrapper = mountModal({ show: true })
    expect(wrapper.find('.n-input').exists()).toBe(true)
    expect(wrapper.find('.paste-modal__result').exists()).toBe(false)
  })

  it('disables Resolve until text is entered', async () => {
    const wrapper = mountModal({ show: true })
    const resolveBtn = wrapper.findAll('.n-button').filter(b =>
      b.text().includes('meetings.participants.resolve'),
    )[0]
    expect(resolveBtn.attributes('disabled')).toBeDefined()

    await wrapper.find('.n-input').setValue('Иванов')
    // После ввода кнопка доступна.
    expect(resolveBtn.attributes('disabled')).toBeUndefined()
  })

  it('calls resolveParticipants with split lines on Resolve click', async () => {
    const wrapper = mountModal({ show: true })
    resolveParticipants.mockResolvedValue({ resolved: [], unresolved: [], ambiguous: [] })

    await wrapper.find('.n-input').setValue('Иванов\na@b.com')
    const resolveBtn = wrapper.findAll('.n-button').filter(b =>
      b.text().includes('meetings.participants.resolve'),
    )[0]
    await resolveBtn.trigger('click')

    expect(resolveParticipants).toHaveBeenCalledWith(['Иванов', 'a@b.com'])
  })

  it('renders resolved/unresolved/ambiguous after resolve', async () => {
    const payload: ResolveParticipantsResponse = {
      resolved: [
        { user_id: 'kc-1', full_name: 'Иван', email: 'ivan@company.com', source: 'keycloak' },
        { user_id: 'ext:ext@partner.com', full_name: 'ext@partner.com', email: 'ext@partner.com', source: 'external' },
      ],
      unresolved: ['Незнакомец'],
      ambiguous: [
        {
          query: 'Петров',
          candidates: [
            { user_id: 'kc-2a', full_name: 'Петров А', email: 'pa@company.com', department: 'IT', position: 'Dev' },
            { user_id: 'kc-2b', full_name: 'Петров Б', email: 'pb@company.com', department: 'HR', position: 'PM' },
          ],
        },
      ],
    }
    resolveParticipants.mockResolvedValue(payload)

    const wrapper = mountModal({ show: true })
    await wrapper.find('.n-input').setValue('Иванов')
    const resolveBtn = wrapper.findAll('.n-button').filter(b =>
      b.text().includes('meetings.participants.resolve'),
    )[0]
    await resolveBtn.trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.paste-modal__result').exists()).toBe(true)
    expect(wrapper.find('.paste-modal__unresolved').text()).toContain('Незнакомец')
    // ambiguous-блок с селектом кандидатов
    expect(wrapper.findAll('.paste-modal__ambiguous')).toHaveLength(1)
  })

  it('emits add with resolved participants (deduped against existingEmails) on Add click', async () => {
    const payload: ResolveParticipantsResponse = {
      resolved: [
        { user_id: 'kc-1', full_name: 'Иван', email: 'ivan@company.com', source: 'keycloak' },
        { user_id: 'kc-2', full_name: 'Пётр', email: 'petr@company.com', source: 'keycloak' },
      ],
      unresolved: [],
      ambiguous: [],
    }
    resolveParticipants.mockResolvedValue(payload)

    // ivan@company.com уже приглашён → должен отфильтроваться.
    const wrapper = mountModal({
      show: true,
      existingEmails: new Set(['ivan@company.com']),
    })
    await wrapper.find('.n-input').setValue('Иванов')
    const resolveBtn = wrapper.findAll('.n-button').filter(b =>
      b.text().includes('meetings.participants.resolve'),
    )[0]
    await resolveBtn.trigger('click')
    await wrapper.vm.$nextTick()

    const addBtn = wrapper.findAll('.n-button').filter(b =>
      b.text().includes('meetings.participants.addResolved'),
    )[0]
    await addBtn.trigger('click')

    const emitted = wrapper.emitted('add')
    expect(emitted).toBeTruthy()
    const added = emitted![0][0] as { email: string }[]
    // ivan@company.com отфильтрован, остался только petr@company.com
    expect(added).toHaveLength(1)
    expect(added[0].email).toBe('petr@company.com')
  })
})
