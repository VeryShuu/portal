import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const messageMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }))

const routeState = vi.hoisted(() => ({ name: 'home' as string | null }))
const authState = vi.hoisted(() => ({ isAuthenticated: true }))

const feedbackApiMock = vi.hoisted(() => ({
  createFeedback: vi.fn(async () => ({ id: 'fb-1' })),
  uploadFeedbackAttachment: vi.fn(async () => ({})),
  FEEDBACK_ATTACHMENT_ACCEPT: 'image/png',
  FEEDBACK_ATTACHMENT_MAX_PER_TICKET: 2,
  FEEDBACK_ATTACHMENT_MAX_SIZE: 10,
}))

const parseApiErrorMock = vi.hoisted(() => ({ parseApiError: vi.fn(() => 'parsed-error') }))

vi.mock('naive-ui', () => ({
  NModal: { template: '<div class="n-modal" v-if="show"><slot /><slot name="footer" /><slot name="action" /></div>', props: ['show', 'preset', 'title', 'maskClosable', 'modelValue'], emits: ['update:show'] },
  NForm: { template: '<form class="n-form" @submit.prevent="$emit(\'submit\', $event)"><slot /></form>', props: ['model', 'labelPlacement'], emits: ['submit'] },
  NFormItem: { template: '<div class="n-form-item"><slot /></div>', props: ['label', 'path'] },
  NInput: { template: '<input class="n-input" :value="value" @input="$emit(\'update:value\', $event.target.value)" @keydown="$emit(\'keydown\', $event)" />', props: ['value', 'placeholder', 'status', 'inputProps', 'clearable', 'type', 'rows', 'maxlength', 'showCount'], emits: ['update:value', 'keydown'] },
  NSelect: { template: '<select class="n-select" :value="value" @change="$emit(\'update:value\', $event.target.value)"><option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option></select>', props: ['value', 'options'], emits: ['update:value'] },
  NButton: { template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /><slot name="icon" /></button>', props: ['type', 'loading', 'disabled', 'size', 'ghost'], emits: ['click'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'size', 'animated'], emits: ['update:value'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NCheckbox: { template: '<label class="n-checkbox"><input type="checkbox" :checked="checked" @change="$emit(\'update:checked\', $event.target.checked)" /><slot /></label>', props: ['checked'], emits: ['update:checked'] },
  useMessage: () => messageMock,
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('../../src/stores/auth', () => ({ useAuthStore: () => authState }))
vi.mock('../../src/api/feedback', () => feedbackApiMock)
vi.mock('../../src/utils/parseApiError', () => parseApiErrorMock)
vi.mock('@/utils/formatSize', () => ({ formatSize: vi.fn((n: number) => `${n}B`) }))
vi.mock('@vicons/ionicons5', () => ({
  AttachOutline: { template: '<span />' },
  ChatbubbleEllipsesOutline: { template: '<span />' },
  CloseOutline: { template: '<span />' },
}))

function mountOpts() {
  return { global: { plugins: [i18n] } }
}

describe('RichEditorLinkModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  async function mountComp(props: Record<string, unknown> = {}, model: Record<string, unknown> = {}) {
    const { default: Comp } = await import('../../src/components/editor/RichEditorLinkModal.vue')
    return mount(Comp, {
      ...mountOpts(),
      props: {
        title: 'Dialog',
        urlStatus: undefined,
        urlError: '',
        showTextField: true,
        editingExisting: false,
        canSubmit: true,
        kbQuery: '',
        kbLoading: false,
        kbMinLength: 2,
        kbResults: [],
        onUrlChange: vi.fn(),
        isInternalKbLink: vi.fn(() => false),
        onKbSearchInput: vi.fn(),
        onKbKeydown: vi.fn(),
        selectKbArticle: vi.fn(),
        highlightKbMatch: vi.fn((title: string) => [{ text: title, match: false }]),
        show: true,
        tab: 'url',
        kbActiveIndex: 0,
        url: 'https://portal.test',
        text: 'Portal',
        newTab: false,
        nofollow: false,
        'onUpdate:show': (v: boolean) => wrapper.setProps({ show: v }),
        'onUpdate:tab': (v: string) => wrapper.setProps({ tab: v }),
        'onUpdate:kbActiveIndex': (v: number) => wrapper.setProps({ kbActiveIndex: v }),
        'onUpdate:url': (v: string) => wrapper.setProps({ url: v }),
        'onUpdate:text': (v: string) => wrapper.setProps({ text: v }),
        'onUpdate:newTab': (v: boolean) => wrapper.setProps({ newTab: v }),
        'onUpdate:nofollow': (v: boolean) => wrapper.setProps({ nofollow: v }),
        ...props,
        ...model,
      },
    })
  }

  let wrapper: any

  it('renders url tab states and emits actions', async () => {
    wrapper = await mountComp({ urlError: 'bad url', showTextField: true, editingExisting: true })
    expect(wrapper.text()).toContain('bad url')
    expect(wrapper.findAll('.n-input').length).toBeGreaterThan(1)

    const removeBtn = wrapper.findAll('.n-button').find((b: any) => b.text().includes('editor.link.remove'))
    await removeBtn!.trigger('click')
    expect(wrapper.emitted('remove')).toBeTruthy()

    const submitBtn = wrapper.findAll('.n-button').find((b: any) => b.text().includes('editor.link.update'))
    await submitBtn!.trigger('click')
    expect(wrapper.emitted('submit')).toBeTruthy()
  })

  it('renders kb tab branches and calls kb handlers', async () => {
    const onKbSearchInput = vi.fn()
    const onKbKeydown = vi.fn()
    const selectKbArticle = vi.fn()
    wrapper = await mountComp({
      tab: 'kb',
      kbQuery: 'ab',
      kbLoading: false,
      kbResults: [{ id: 'a1', title: 'Article', status: 'draft' }],
      onKbSearchInput,
      onKbKeydown,
      selectKbArticle,
      highlightKbMatch: (title: string) => [{ text: title, match: true }],
    })

    const searchInput = wrapper.findAll('.n-input').at(-1)!
    expect(searchInput.exists()).toBe(true)
    await searchInput.setValue('abc')
    await searchInput.trigger('keydown', { key: 'ArrowDown' })
    expect(onKbSearchInput).toHaveBeenCalled()
    expect(onKbKeydown).toHaveBeenCalled()

    const kbBtn = wrapper.find('.kb-search-item')
    await kbBtn.trigger('mouseenter')
    await kbBtn.trigger('click')
    expect(selectKbArticle).toHaveBeenCalled()

    await wrapper.setProps({ kbLoading: true })
    await nextTick()
    expect(wrapper.text()).toContain('common.loading')

    await wrapper.setProps({ kbLoading: false, kbResults: [], kbQuery: 'zz' })
    await nextTick()
    expect(wrapper.text()).toContain('editor.link.kbNoResults')
  })
})

describe('FeedbackModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.isAuthenticated = true
    routeState.name = 'home'
  })

  async function mountComp() {
    const { default: Comp } = await import('../../src/components/FeedbackModal.vue')
    return mount(Comp, mountOpts())
  }

  it('hides floating button for unauthenticated or hidden routes', async () => {
    authState.isAuthenticated = false
    let wrapper = await mountComp()
    expect(wrapper.find('.fb-fab').exists()).toBe(false)

    authState.isAuthenticated = true
    routeState.name = 'login'
    wrapper = await mountComp()
    expect(wrapper.find('.fb-fab').exists()).toBe(false)
  })

  it('opens modal and submits feedback with successful attachments', async () => {
    const wrapper = await mountComp()
    await wrapper.find('.fb-fab').trigger('click')
    expect(wrapper.find('.n-modal').exists()).toBe(true)

    const messageInput = wrapper.findAll('.n-input')[0]
    await messageInput.setValue('Bug message')

    const fileInput = wrapper.find('input[type="file"]')
    const okFile = new File(['a'], 'ok.png', { type: 'image/png' })
    Object.defineProperty(fileInput.element, 'files', { value: [okFile], configurable: true })
    await fileInput.trigger('change')

    const submitBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('feedback.submit'))
    await submitBtn!.trigger('click')
    await flushPromises()

    expect(feedbackApiMock.createFeedback).toHaveBeenCalled()
    expect(feedbackApiMock.uploadFeedbackAttachment).toHaveBeenCalledWith('fb-1', okFile)
    expect(messageMock.success).toHaveBeenCalledWith('feedback.successMessage')
  })

  it('handles attachment limits, partial upload failure and submit error', async () => {
    const wrapper = await mountComp()
    await wrapper.find('.fb-fab').trigger('click')

    const fileInput = wrapper.find('input[type="file"]')
    const large = new File(['toolargecontent'], 'big.png', { type: 'image/png' })
    Object.defineProperty(large, 'size', { value: 99 })
    Object.defineProperty(fileInput.element, 'files', { value: [large], configurable: true })
    await fileInput.trigger('change')
    expect(messageMock.error).toHaveBeenCalled()

    const ok1 = new File(['1'], '1.png', { type: 'image/png' })
    const ok2 = new File(['2'], '2.png', { type: 'image/png' })
    const ok3 = new File(['3'], '3.png', { type: 'image/png' })
    Object.defineProperty(fileInput.element, 'files', { value: [ok1, ok2, ok3], configurable: true })
    await fileInput.trigger('change')
    expect(messageMock.warning).toHaveBeenCalled()

    const messageInput = wrapper.findAll('.n-input')[0]
    await messageInput.setValue('Need help')

    feedbackApiMock.uploadFeedbackAttachment.mockRejectedValueOnce(new Error('upload fail'))
    const submitBtn = wrapper.findAll('.n-button').find((b) => b.text().includes('feedback.submit'))
    await submitBtn!.trigger('click')
    await flushPromises()
    expect(messageMock.warning).toHaveBeenCalledWith('feedback.attachUploadPartial')

    feedbackApiMock.createFeedback.mockRejectedValueOnce(new Error('submit fail'))
    await wrapper.find('.fb-fab').trigger('click')
    const messageInput2 = wrapper.findAll('.n-input')[0]
    await messageInput2.setValue('Need help again')
    const submitBtn2 = wrapper.findAll('.n-button').find((b) => b.text().includes('feedback.submit'))
    await submitBtn2!.trigger('click')
    await flushPromises()
    expect(messageMock.error).toHaveBeenCalledWith('parsed-error')
  })
})
