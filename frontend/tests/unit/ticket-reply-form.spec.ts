/**
 * Unit-тесты TicketReplyForm.vue — форма ответа тикета helpdesk.
 *
 * Покрытие (миграция 083, «Ответить всем»):
 * - включение чекбокса pre-fill'ит ccRecipients из участников тикета
 *   (минус requester; участник без name → name: null)
 * - выключение чекбокса очищает список
 * - submit передаёт cc как string[] email'ов только при включённом replyAll
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

vi.mock('naive-ui', () => ({
  NButton: {
    template:
      '<button class="n-button" :disabled="disabled" @click="$emit(\'click\', $event)"><slot name="icon" /><slot /></button>',
    props: ['type', 'loading', 'disabled', 'quaternary'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  NUpload: {
    template: '<div class="n-upload"><slot /></div>',
    props: ['fileList', 'max', 'multiple', 'defaultUpload'],
    emits: ['update:fileList'],
  },
  NCheckbox: {
    template:
      '<input type="checkbox" class="n-checkbox" :checked="checked" :disabled="disabled" @change="$emit(\'update:checked\', $event.target.checked)" />',
    props: ['checked', 'disabled', 'size'],
    emits: ['update:checked'],
  },
}))

vi.mock('@vicons/ionicons5', () => ({
  AttachOutline: { template: '<i class="attach-icon" />' },
}))

vi.mock('../../src/components/RichEditor.vue', () => ({
  default: {
    name: 'RichEditor',
    template: '<div class="rich-editor" />',
    props: ['modelValue', 'placeholder', 'uploadEndpoint'],
    emits: ['update:modelValue'],
  },
}))

vi.mock('../../src/components/helpdesk/CcRecipientPicker.vue', () => ({
  default: {
    name: 'CcRecipientPicker',
    template: '<div class="cc-picker" />',
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue'],
  },
}))

vi.mock('../../src/utils/markdown', () => ({
  mdUnsafe: { render: (src: string) => `<p>${src}</p>` },
}))

import TicketReplyForm from '../../src/components/helpdesk/TicketReplyForm.vue'
import type { HelpdeskParticipant } from '../../src/api/helpdesk'

const PARTICIPANTS: HelpdeskParticipant[] = [
  { email: 'requester@company.local', is_requester: true, name: 'Заявитель' },
  { email: 'cc-one@company.local', is_requester: false, name: undefined },
  { email: 'cc-two@company.local', is_requester: false, name: 'Второй Копия' },
]

function mountForm(props: Record<string, unknown> = {}) {
  return mount(TicketReplyForm, {
    props: {
      agentMode: true,
      ticketId: 'ticket-7',
      participants: PARTICIPANTS,
      ...props,
    },
  })
}

async function setReplyAll(wrapper: ReturnType<typeof mountForm>, on: boolean) {
  await wrapper.find('input.n-checkbox').setValue(on)
}

describe('TicketReplyForm.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('replyAll pre-fill: requester исключён, участник без name → name: null', async () => {
    const wrapper = mountForm()
    await setReplyAll(wrapper, true)

    const picker = wrapper.findComponent({ name: 'CcRecipientPicker' })
    expect(picker.exists()).toBe(true)
    expect(picker.props('modelValue')).toEqual([
      { email: 'cc-one@company.local', name: null, source: 'directory' },
      { email: 'cc-two@company.local', name: 'Второй Копия', source: 'directory' },
    ])
  })

  it('выключение replyAll очищает список копий', async () => {
    const wrapper = mountForm()
    await setReplyAll(wrapper, true)
    await setReplyAll(wrapper, false)

    const picker = wrapper.findComponent({ name: 'CcRecipientPicker' })
    expect(picker.exists()).toBe(false)
  })

  it('submit передаёт cc как список email-адресов только при включённом replyAll', async () => {
    const wrapper = mountForm()

    // Без «Ответить всем» — cc отсутствует в payload.
    wrapper.findComponent({ name: 'RichEditor' }).vm.$emit('update:modelValue', 'Первый ответ')
    await nextTick() // кнопка submit снимает :disabled после появления текста
    await wrapper.findAll('.n-button').at(-1)!.trigger('click')
    expect(wrapper.emitted('submit')).toBeTruthy()
    expect(wrapper.emitted<[payload: { cc?: string[] }]>('submit')![0][0].cc).toBeUndefined()

    // С «Ответить всем» — cc = string[] email'ов.
    await setReplyAll(wrapper, true)
    wrapper.findComponent({ name: 'RichEditor' }).vm.$emit('update:modelValue', 'Ответ всем')
    await nextTick()
    await wrapper.findAll('.n-button').at(-1)!.trigger('click')
    const payloads = wrapper.emitted<[payload: { cc?: string[] }]>('submit')!
    expect(payloads[payloads.length - 1][0].cc).toEqual([
      'cc-one@company.local',
      'cc-two@company.local',
    ])
  })
})
