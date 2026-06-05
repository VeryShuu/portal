import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en: {}, ru: {} } })

const h = vi.hoisted(() => {
  const state = { markdown: '<p>initial</p>' }
  const setContent = vi.fn((val: string) => { state.markdown = val })
  const openLinkDialog = vi.fn()
  const triggerImageUpload = vi.fn()
  const openImageDialogForEdit = vi.fn()
  const openDetailsDialog = vi.fn()
  let onUpdate: ((p: { editor: unknown }) => void) | undefined
  let shouldShow: ((p: { editor: unknown; from: number; to: number }) => boolean) | undefined
  const editor = {
    isActive: vi.fn(() => false),
    chain: () => ({ focus: () => ({ toggleBold: () => ({ run: vi.fn() }) }) }),
    storage: { markdown: { getMarkdown: () => state.markdown } },
    commands: { setContent },
    destroy: vi.fn(),
  }
  return {
    state, setContent, editor,
    openLinkDialog, triggerImageUpload, openImageDialogForEdit, openDetailsDialog,
    setOnUpdate: (fn: typeof onUpdate) => { onUpdate = fn },
    getOnUpdate: () => onUpdate,
    setShouldShow: (fn: typeof shouldShow) => { shouldShow = fn },
    getShouldShow: () => shouldShow,
  }
})

vi.mock('@tiptap/vue-3', () => ({
  useEditor: vi.fn((opts: { onUpdate?: (p: { editor: unknown }) => void }) => {
    h.setOnUpdate(opts?.onUpdate)
    return { value: h.editor }
  }),
  EditorContent: {
    name: 'EditorContent',
    template: '<div class="editor-content-stub"><figure data-type="figure-image" class="fig"></figure></div>',
  },
  BubbleMenu: {
    name: 'BubbleMenu',
    props: ['editor', 'shouldShow', 'tippyOptions'],
    setup(props: { shouldShow?: (p: { editor: unknown; from: number; to: number }) => boolean }) {
      h.setShouldShow(props.shouldShow)
      return () => null
    },
  },
}))

vi.mock('../../src/components/editor/extensions', () => ({ buildEditorExtensions: () => [] }))

vi.mock('naive-ui', () => ({
  NButton: { name: 'NButton', template: '<button><slot /></button>' },
  NButtonGroup: { name: 'NButtonGroup', template: '<div><slot /></div>' },
  NCheckbox: { name: 'NCheckbox', template: '<div><slot /></div>' },
  NModal: { name: 'NModal', props: ['show'], template: '<div v-if="show" class="modal"><slot /></div>' },
  NInput: { name: 'NInput', template: '<input />' },
  NTabs: { name: 'NTabs', template: '<div><slot /></div>' },
  NTabPane: { name: 'NTabPane', template: '<div><slot /></div>' },
}))

vi.mock('../../src/components/editor/toolbar/RichEditorToolbar.vue', () => ({
  default: {
    name: 'RichEditorToolbar',
    props: ['editor', 'fullscreen', 'focusMode'],
    emits: ['open-link', 'insert-image', 'open-video', 'open-details', 'toggle-fullscreen', 'toggle-focus'],
    template: `<div>
      <button aria-label="open-link" @click="$emit('open-link')">l</button>
      <button aria-label="insert-image" @click="$emit('insert-image')">i</button>
      <button aria-label="open-video" @click="$emit('open-video')">v</button>
      <button aria-label="open-details" @click="$emit('open-details')">d</button>
      <button aria-label="toggle-fullscreen" @click="$emit('toggle-fullscreen')">fs</button>
      <button aria-label="toggle-focus" @click="$emit('toggle-focus')">fc</button>
    </div>`,
  },
}))

vi.mock('../../src/components/editor/useEditorLinkDialog', () => ({
  useEditorLinkDialog: () => ({
    showLinkDialog: false, linkEditingExisting: false, linkForm: { url: '', text: '', newTab: false, nofollow: false }, linkUrlError: '',
    linkDialogTitle: '', linkShowTextField: false, linkUrlStatus: undefined, canSubmitLink: false,
    onLinkUrlChange: vi.fn(), openLinkDialog: h.openLinkDialog, submitLink: vi.fn(), removeLink: vi.fn(),
    linkTab: 'url', kbSearchQuery: '', kbSearchResults: [], kbSearchLoading: false, kbActiveIndex: -1,
    onKbSearchInput: vi.fn(), onKbKeydown: vi.fn(), selectKbArticle: vi.fn(),
    highlightKbMatch: vi.fn(() => []), isInternalKbLink: vi.fn(() => false), kbMinLength: 2,
  }),
}))

vi.mock('../../src/components/editor/useEditorImageUpload', () => ({
  useEditorImageUpload: () => ({
    fileInputRef: { value: null }, triggerImageUpload: h.triggerImageUpload, handleFileInputChange: vi.fn(),
    handleDrop: vi.fn(), handlePaste: vi.fn(), showImageDialog: false,
    imageForm: { src: '', alt: '', caption: '' }, openImageDialogForEdit: h.openImageDialogForEdit,
    submitImageDialog: vi.fn(), cancelImageDialog: vi.fn(),
  }),
}))

vi.mock('../../src/components/editor/useEditorVideoDialog', async () => {
  const { ref } = await import('vue')
  return {
    useEditorVideoDialog: () => ({ showVideoDialog: ref(false), videoUrl: ref(''), insertVideo: vi.fn() }),
  }
})

vi.mock('../../src/components/editor/useEditorDetailsDialog', () => ({
  useEditorDetailsDialog: () => ({
    showDetailsDialog: false, detailsSummary: '',
    openDetailsDialog: h.openDetailsDialog, insertDetails: vi.fn(), preventDetailsToggle: vi.fn(),
  }),
}))

async function mountEditor(props: Record<string, unknown> = {}) {
  const { default: RichEditor } = await import('../../src/components/RichEditor.vue')
  return mount(RichEditor, {
    props: { modelValue: 'hello', ...props },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })
}

describe('RichEditor shell (RE-0 characterizing)', () => {
  beforeEach(() => {
    h.state.markdown = 'hello'
    h.setContent.mockClear()
    h.openLinkDialog.mockClear()
    h.triggerImageUpload.mockClear()
    h.openImageDialogForEdit.mockClear()
    h.openDetailsDialog.mockClear()
  })

  it('passes initial modelValue to useEditor content', async () => {
    const { useEditor } = await import('@tiptap/vue-3')
    await mountEditor({ modelValue: 'seed' })
    const calls = (useEditor as ReturnType<typeof vi.fn>).mock.calls
    expect(calls[calls.length - 1][0].content).toBe('seed')
  })

  it('emits update:modelValue from editor onUpdate', async () => {
    const wrapper = await mountEditor()
    h.state.markdown = 'edited'
    h.getOnUpdate()?.({ editor: h.editor })
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted?.[0]?.[0]).toBe('edited')
  })

  it('v-model sync: prop change differing from editor calls setContent(val, false)', async () => {
    const wrapper = await mountEditor({ modelValue: 'hello' })
    await wrapper.setProps({ modelValue: 'external change' })
    expect(h.setContent).toHaveBeenCalledWith('external change', false)
  })

  it('v-model sync: prop equal to editor markdown does NOT call setContent (no loop)', async () => {
    const wrapper = await mountEditor({ modelValue: 'hello' })
    h.state.markdown = 'same'
    await wrapper.setProps({ modelValue: 'same' })
    expect(h.setContent).not.toHaveBeenCalled()
  })

  it('toggle-fullscreen adds/removes is-fullscreen class', async () => {
    const wrapper = await mountEditor()
    expect(wrapper.find('.editor-wrap').classes()).not.toContain('is-fullscreen')
    await wrapper.find('button[aria-label="toggle-fullscreen"]').trigger('click')
    expect(wrapper.find('.editor-wrap').classes()).toContain('is-fullscreen')
    await wrapper.find('button[aria-label="toggle-fullscreen"]').trigger('click')
    expect(wrapper.find('.editor-wrap').classes()).not.toContain('is-fullscreen')
  })

  it('toggle-focus adds is-focus class', async () => {
    const wrapper = await mountEditor()
    await wrapper.find('button[aria-label="toggle-focus"]').trigger('click')
    expect(wrapper.find('.editor-wrap').classes()).toContain('is-focus')
  })

  it('Escape key exits fullscreen', async () => {
    const wrapper = await mountEditor()
    await wrapper.find('button[aria-label="toggle-fullscreen"]').trigger('click')
    expect(wrapper.find('.editor-wrap').classes()).toContain('is-fullscreen')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.editor-wrap').classes()).not.toContain('is-fullscreen')
  })

  it('Escape key while not fullscreen is a no-op', async () => {
    const wrapper = await mountEditor()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.editor-wrap').classes()).not.toContain('is-fullscreen')
  })

  it('toolbar events delegate to composable handlers', async () => {
    const wrapper = await mountEditor()
    await wrapper.find('button[aria-label="open-link"]').trigger('click')
    expect(h.openLinkDialog).toHaveBeenCalled()
    await wrapper.find('button[aria-label="insert-image"]').trigger('click')
    expect(h.triggerImageUpload).toHaveBeenCalled()
    await wrapper.find('button[aria-label="open-details"]').trigger('click')
    expect(h.openDetailsDialog).toHaveBeenCalled()
  })

  it('open-video toolbar event opens video modal', async () => {
    const wrapper = await mountEditor()
    await wrapper.find('button[aria-label="open-video"]').trigger('click')
    expect(wrapper.html()).toContain('class="modal"')
  })

  it('dblclick on figure opens image edit dialog', async () => {
    const wrapper = await mountEditor()
    await wrapper.find('figure.fig').trigger('dblclick')
    expect(h.openImageDialogForEdit).toHaveBeenCalled()
  })

  it('shouldShowBubbleMenu reflects selection and active node rules', async () => {
    await mountEditor()
    const fn = h.getShouldShow()
    expect(fn).toBeTypeOf('function')
    const ed = (active: string | null, text: string) => ({
      isEditable: true,
      isActive: (n: string) => n === active,
      state: { doc: { textBetween: () => text } },
    })
    expect(fn!({ editor: ed(null, 'hi'), from: 0, to: 2 })).toBe(true)
    expect(fn!({ editor: ed(null, 'hi'), from: 2, to: 2 })).toBe(false)
    expect(fn!({ editor: ed('image', 'hi'), from: 0, to: 2 })).toBe(false)
    expect(fn!({ editor: ed(null, '   '), from: 0, to: 3 })).toBe(false)
    expect(fn!({ editor: { ...ed(null, 'hi'), isEditable: false }, from: 0, to: 2 })).toBe(false)
  })

  it('removes window keydown listener on unmount', async () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    const wrapper = await mountEditor()
    wrapper.unmount()
    expect(removeSpy).toHaveBeenCalledWith('keydown', expect.any(Function))
    removeSpy.mockRestore()
  })
})
