import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false, messages: { en: {}, ru: {} } })

let updateCallback: ((md: string) => void) | undefined
let editorContentRef = '<p>initial</p>'

const mockEditor = {
  isActive: vi.fn(() => false),
  chain: () => ({
    focus: () => ({
      toggleBold: () => ({ run: vi.fn() }),
      toggleItalic: () => ({ run: vi.fn() }),
    }),
  }),
  getHTML: () => editorContentRef,
  storage: {
    markdown: {
      getMarkdown: () => editorContentRef,
    },
  },
  commands: { setContent: vi.fn((val: string) => { editorContentRef = val }) },
  destroy: vi.fn(),
}

vi.mock('@tiptap/vue-3', () => ({
  useEditor: vi.fn((opts: { onUpdate?: (p: { editor: typeof mockEditor }) => void }) => {
    updateCallback = opts?.onUpdate
      ? (md: string) => opts.onUpdate!({ editor: { ...mockEditor, storage: { markdown: { getMarkdown: () => md } } } })
      : undefined
    return { value: mockEditor }
  }),
  EditorContent: { name: 'EditorContent', render: () => null },
  BubbleMenu: { name: 'BubbleMenu', render: () => null },
}))

vi.mock('@tiptap/starter-kit', () => ({ default: { configure: () => ({}) } }))
vi.mock('@tiptap/extension-placeholder', () => ({ default: { configure: () => ({}) } }))
vi.mock('@tiptap/extension-link', () => ({ default: { configure: () => ({}) } }))
vi.mock('@tiptap/extension-image', () => ({ default: {} }))
vi.mock('@tiptap/extension-text-align', () => ({ default: { configure: () => ({}) } }))
vi.mock('@tiptap/extension-table', () => ({ default: { configure: () => ({}) } }))
vi.mock('@tiptap/extension-table-row', () => ({ default: {} }))
vi.mock('@tiptap/extension-table-header', () => ({ default: {} }))
vi.mock('@tiptap/extension-table-cell', () => ({ default: {} }))
vi.mock('@tiptap/extension-underline', () => ({ default: {} }))
vi.mock('@tiptap/extension-subscript', () => ({ default: {} }))
vi.mock('@tiptap/extension-superscript', () => ({ default: {} }))
vi.mock('@tiptap/extension-highlight', () => ({ default: { configure: () => ({}) } }))
vi.mock('@tiptap/extension-focus', () => ({ default: { configure: () => ({}) } }))
vi.mock('@tiptap/extension-task-list', () => ({ default: {} }))
vi.mock('@tiptap/extension-task-item', () => ({ default: { configure: () => ({}) } }))
vi.mock('tiptap-markdown', () => ({ Markdown: { configure: () => ({}) } }))
vi.mock('../../src/components/editor/extensions/FigureImage', () => ({ FigureImage: {} }))
vi.mock('../../src/components/editor/extensions/IframeEmbed', () => ({ IframeEmbed: {} }))
vi.mock('../../src/components/editor/extensions/AlignedNodes', () => ({ AlignedParagraph: {}, AlignedHeading: {} }))
vi.mock('../../src/components/editor/extensions/Callout', () => ({ Callout: {} }))
vi.mock('../../src/components/editor/extensions/Details', () => ({ Details: {} }))

vi.mock('naive-ui', () => ({
  NButton: { name: 'NButton', render: () => null },
  NButtonGroup: { name: 'NButtonGroup', render: () => null },
  NCheckbox: { name: 'NCheckbox', render: () => null },
  NModal: { name: 'NModal', render: () => null },
  NInput: { name: 'NInput', render: () => null },
  NTabs: { name: 'NTabs', render: () => null },
  NTabPane: { name: 'NTabPane', render: () => null },
}))

vi.mock('../../src/components/editor/toolbar/RichEditorToolbar.vue', () => ({
  default: {
    name: 'RichEditorToolbar',
    props: ['editor', 'fullscreen', 'focusMode'],
    emits: ['open-link', 'insert-image', 'open-video', 'open-details', 'toggle-fullscreen', 'toggle-focus'],
    template: `<div>
      <button aria-label="open-link" @click="$emit('open-link')">link</button>
      <button aria-label="insert-image" @click="$emit('insert-image')">image</button>
      <button aria-label="toggle-fullscreen" @click="$emit('toggle-fullscreen')">fs</button>
    </div>`,
  },
}))

vi.mock('../../src/components/editor/useEditorLinkDialog', () => ({
  useEditorLinkDialog: () => ({
    showLinkDialog: false, linkEditingExisting: false, linkForm: { url: '', text: '', newTab: false, nofollow: false }, linkUrlError: '',
    linkDialogTitle: '', linkShowTextField: false, linkUrlStatus: 'default', canSubmitLink: false,
    onLinkUrlChange: vi.fn(), openLinkDialog: vi.fn(), submitLink: vi.fn(), removeLink: vi.fn(),
    linkTab: 'url', kbSearchQuery: '', kbSearchResults: [], kbSearchLoading: false, kbActiveIndex: -1,
    onKbSearchInput: vi.fn(), onKbKeydown: vi.fn(), selectKbArticle: vi.fn(),
    highlightKbMatch: vi.fn(() => []), isInternalKbLink: vi.fn(() => false), kbMinLength: 2,
  }),
}))

vi.mock('../../src/components/editor/useEditorImageUpload', () => ({
  useEditorImageUpload: () => ({
    fileInputRef: { value: null }, triggerImageUpload: vi.fn(), handleFileInputChange: vi.fn(),
    handleDrop: vi.fn(), handlePaste: vi.fn(), showImageDialog: false,
    imageForm: { src: '', alt: '', caption: '' }, openImageDialogForEdit: vi.fn(),
    submitImageDialog: vi.fn(), cancelImageDialog: vi.fn(),
  }),
}))

vi.mock('../../src/components/editor/useEditorVideoDialog', () => ({
  useEditorVideoDialog: () => ({ showVideoDialog: false, videoUrl: '', insertVideo: vi.fn() }),
}))

vi.mock('../../src/components/editor/useEditorDetailsDialog', () => ({
  useEditorDetailsDialog: () => ({
    showDetailsDialog: false, detailsSummary: '',
    openDetailsDialog: vi.fn(), insertDetails: vi.fn(), preventDetailsToggle: vi.fn(),
  }),
}))

describe('RichEditor', () => {
  it('imports without errors', async () => {
    const mod = await import('../../src/components/RichEditor.vue')
    expect(mod.default).toBeDefined()
  })

  it('renders with modelValue prop and passes content to editor', async () => {
    const { default: RichEditor } = await import('../../src/components/RichEditor.vue')
    const wrapper = mount(RichEditor, {
      props: { modelValue: 'hello world' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('emits update:modelValue when editor content changes', async () => {
    const { useEditor } = await import('@tiptap/vue-3')
    const { default: RichEditor } = await import('../../src/components/RichEditor.vue')
    const wrapper = mount(RichEditor, {
      props: { modelValue: '' },
      global: { plugins: [i18n] },
    })
    const calls = (useEditor as ReturnType<typeof vi.fn>).mock.calls
    const lastCall = calls[calls.length - 1]
    const onUpdate = lastCall?.[0]?.onUpdate
    if (onUpdate) {
      onUpdate({ editor: { ...mockEditor, storage: { markdown: { getMarkdown: () => 'new content' } } } })
    }
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toBe('new content')
  })

  it('propagates toggle-fullscreen from toolbar', async () => {
    const { default: RichEditor } = await import('../../src/components/RichEditor.vue')
    const wrapper = mount(RichEditor, {
      props: { modelValue: '' },
      global: { plugins: [i18n] },
    })
    const toolbar = wrapper.findComponent({ name: 'RichEditorToolbar' })
    expect(toolbar.exists()).toBe(true)
    await toolbar.find('button[aria-label="toggle-fullscreen"]').trigger('click')
    expect(wrapper.find('.editor-wrap').classes()).toContain('editor-wrap')
  })
})
