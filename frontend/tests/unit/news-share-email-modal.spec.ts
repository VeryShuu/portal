import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru: {}, en: {} },
})

const message = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }

vi.mock('naive-ui', () => ({
  NModal: { template: '<div class="n-modal" v-if="show"><slot /><slot name="footer" /></div>', props: ['show', 'title', 'preset', 'maskClosable'], emits: ['update:show'] },
  NForm: { template: '<form><slot /></form>', props: ['model', 'rules', 'labelPlacement'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path', 'feedback', 'validationStatus'] },
  NSelect: {
    name: 'NSelect',
    template: '<select class="n-select" multiple><slot /></select>',
    props: ['value', 'options', 'loading', 'placeholder', 'multiple', 'filterable', 'maxTagCount'],
    emits: ['update:value'],
  },
  NInput: { template: '<textarea class="n-input" :value="value" @input="$emit(\'update:value\', $event.target.value)" />', props: ['value', 'type', 'autosize', 'maxlength', 'showCount', 'placeholder'], emits: ['update:value'] },
  NButton: { template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>', props: ['type', 'disabled', 'loading'], emits: ['click'] },
  useMessage: () => message,
}))

const useMailingRecipientsQueryMock = vi.fn()
const shareMutateAsync = vi.fn()
const sharePending = ref(false)

vi.mock('../../src/queries/mailingRecipients', () => ({
  useMailingRecipientsQuery: (...args: unknown[]) => useMailingRecipientsQueryMock(...args),
}))
vi.mock('../../src/queries/news', () => ({
  useShareNewsEmailMutation: () => ({
    mutateAsync: shareMutateAsync,
    isPending: sharePending,
  }),
}))

import NewsShareEmailModal from '../../src/components/news/NewsShareEmailModal.vue'

const globalPlugins = { plugins: [i18n] }

function mountModal(props: Record<string, unknown> = {}) {
  return mount(NewsShareEmailModal, {
    props: {
      show: true,
      newsId: 'n-1',
      newsTitle: 'Заголовок',
      newsBody: '# Привет\n\n**жирный** текст [ссылка](http://x)',
      ...props,
    },
    global: globalPlugins,
  })
}

describe('NewsShareEmailModal', () => {
  beforeEach(() => {
    message.success.mockReset()
    message.error.mockReset()
    shareMutateAsync.mockReset()
    sharePending.value = false
    useMailingRecipientsQueryMock.mockReturnValue({
      data: ref({ items: [
        { id: 'r-1', name: 'Alice', email: 'a@x.local', label: 'HR' },
        { id: 'r-2', name: 'Bob', email: 'b@x.local', label: null },
      ], total: 2, limit: 500, offset: 0 }),
      isLoading: ref(false),
    })
  })

  it('builds recipient options with name, email and label', async () => {
    const wrapper = mountModal()
    await flushPromises()
    const select = wrapper.findComponent({ name: 'NSelect' })
    const options = select.props('options') as Array<{ label: string; value: string }>
    expect(options).toHaveLength(2)
    expect(options[0].label).toContain('Alice')
    expect(options[0].label).toContain('a@x.local')
    expect(options[0].label).toContain('HR')
    expect(options[0].value).toBe('r-1')
  })

  it('prefills the message textarea with a stripped excerpt on open', async () => {
    const wrapper = mountModal({ show: false })
    await wrapper.setProps({ show: true })
    await flushPromises()
    const textarea = wrapper.find('textarea.n-input')
    const val = (textarea.element as HTMLTextAreaElement).value
    expect(val).toContain('Привет')
    expect(val).toContain('жирный')
    expect(val).not.toContain('#')
    expect(val).not.toContain('http://x')
  })

  it('shows validation error and does not send when no recipient selected', async () => {
    const wrapper = mountModal()
    await flushPromises()
    const sendBtn = wrapper.findAll('.n-button').at(-1)
    await sendBtn!.trigger('click')
    await flushPromises()
    expect(shareMutateAsync).not.toHaveBeenCalled()
  })

  it('sends to selected recipients and emits close on success', async () => {
    shareMutateAsync.mockResolvedValue({ enqueued: 2 })
    const wrapper = mountModal()
    await flushPromises()

    const select = wrapper.findComponent({ name: 'NSelect' })
    select.vm.$emit('update:value', ['r-1', 'r-2'])
    await flushPromises()

    const sendBtn = wrapper.findAll('.n-button').at(-1)
    await sendBtn!.trigger('click')
    await flushPromises()

    expect(shareMutateAsync).toHaveBeenCalledWith({
      newsId: 'n-1',
      dto: expect.objectContaining({ recipient_ids: ['r-1', 'r-2'] }),
    })
    expect(message.success).toHaveBeenCalled()
    expect(wrapper.emitted('update:show')?.some((e) => e[0] === false)).toBe(true)
  })

  it('shows notPublished error on 409', async () => {
    shareMutateAsync.mockRejectedValue({ response: { status: 409 } })
    const wrapper = mountModal()
    await flushPromises()

    const select = wrapper.findComponent({ name: 'NSelect' })
    select.vm.$emit('update:value', ['r-1'])
    await flushPromises()

    const sendBtn = wrapper.findAll('.n-button').at(-1)
    await sendBtn!.trigger('click')
    await flushPromises()

    expect(message.error).toHaveBeenCalled()
  })
})
