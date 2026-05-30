/**
 * Unit-тесты RichEditorToolbar.vue: проверяют клики ключевых команд
 * (bold/italic/heading/list) и emit-события (link/image/video/details/fullscreen).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button :aria-label="ariaLabel" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'quaternary', 'ariaLabel'],
    emits: ['click'],
  },
  NButtonGroup: { template: '<div class="n-button-group"><slot /></div>', props: ['size'] },
  NDropdown: {
    template: '<div class="n-dropdown" @click="$emit(\'select\', simulateKey)"><slot /></div>',
    props: ['trigger', 'options'],
    emits: ['select'],
    data() { return { simulateKey: '' } },
  },
  NTooltip: { template: '<div><slot /><slot name="trigger" /></div>' },
}))

interface ChainMock {
  focus: () => ChainMock
  toggleBold: () => ChainMock
  toggleItalic: () => ChainMock
  toggleStrike: () => ChainMock
  toggleUnderline: () => ChainMock
  toggleCode: () => ChainMock
  toggleHighlight: () => ChainMock
  toggleSubscript: () => ChainMock
  toggleSuperscript: () => ChainMock
  toggleHeading: (opts: { level: number }) => ChainMock
  toggleBulletList: () => ChainMock
  toggleOrderedList: () => ChainMock
  toggleTaskList: () => ChainMock
  toggleBlockquote: () => ChainMock
  toggleCodeBlock: () => ChainMock
  setTextAlign: (a: string) => ChainMock
  setHorizontalRule: () => ChainMock
  insertTable: (opts: unknown) => ChainMock
  addColumnBefore: () => ChainMock
  toggleCallout: (k: string) => ChainMock
  run: () => boolean
}

function makeChain(calls: string[]): ChainMock {
  const proxy = new Proxy({} as Record<string, unknown>, {
    get(_t, prop: string) {
      if (prop === 'run') return () => true
      return (...args: unknown[]) => {
        calls.push(args.length ? `${prop}:${JSON.stringify(args)}` : prop)
        return proxy
      }
    },
  })
  return proxy as unknown as ChainMock
}

function makeEditor(calls: string[]) {
  return {
    isActive: vi.fn(() => false),
    chain: () => makeChain(calls),
  }
}

describe('RichEditorToolbar.vue', () => {
  let calls: string[]

  beforeEach(() => {
    calls = []
  })

  it('toggles bold via chain().focus().toggleBold().run()', async () => {
    const { default: Toolbar } = await import('../../src/components/editor/toolbar/RichEditorToolbar.vue')
    const wrapper = mount(Toolbar, {
      props: { editor: makeEditor(calls) },
      global: { plugins: [i18n] },
    })
    const btn = wrapper.find('button[aria-label="editor.bold"]')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    expect(calls).toContain('focus')
    expect(calls).toContain('toggleBold')
  })

  it('toggles italic when clicked', async () => {
    const { default: Toolbar } = await import('../../src/components/editor/toolbar/RichEditorToolbar.vue')
    const wrapper = mount(Toolbar, {
      props: { editor: makeEditor(calls) },
      global: { plugins: [i18n] },
    })
    await wrapper.find('button[aria-label="editor.italic"]').trigger('click')
    expect(calls).toContain('toggleItalic')
  })

  it('toggles heading2 with level=2', async () => {
    const { default: Toolbar } = await import('../../src/components/editor/toolbar/RichEditorToolbar.vue')
    const wrapper = mount(Toolbar, {
      props: { editor: makeEditor(calls) },
      global: { plugins: [i18n] },
    })
    await wrapper.find('button[aria-label="editor.heading2"]').trigger('click')
    const headingCall = calls.find(c => c.startsWith('toggleHeading'))
    expect(headingCall).toBeDefined()
    expect(headingCall).toContain('"level":2')
  })

  it('toggles bullet list', async () => {
    const { default: Toolbar } = await import('../../src/components/editor/toolbar/RichEditorToolbar.vue')
    const wrapper = mount(Toolbar, {
      props: { editor: makeEditor(calls) },
      global: { plugins: [i18n] },
    })
    await wrapper.find('button[aria-label="editor.bulletList"]').trigger('click')
    expect(calls).toContain('toggleBulletList')
  })

  it('emits open-link when link button clicked', async () => {
    const { default: Toolbar } = await import('../../src/components/editor/toolbar/RichEditorToolbar.vue')
    const wrapper = mount(Toolbar, {
      props: { editor: makeEditor(calls) },
      global: { plugins: [i18n] },
    })
    await wrapper.find('button[aria-label="editor.insert_link"]').trigger('click')
    expect(wrapper.emitted('open-link')).toBeTruthy()
  })

  it('emits insert-image when image button clicked', async () => {
    const { default: Toolbar } = await import('../../src/components/editor/toolbar/RichEditorToolbar.vue')
    const wrapper = mount(Toolbar, {
      props: { editor: makeEditor(calls) },
      global: { plugins: [i18n] },
    })
    await wrapper.find('button[aria-label="editor.insert_image"]').trigger('click')
    expect(wrapper.emitted('insert-image')).toBeTruthy()
  })

  it('emits toggle-fullscreen when fullscreen button clicked', async () => {
    const { default: Toolbar } = await import('../../src/components/editor/toolbar/RichEditorToolbar.vue')
    const wrapper = mount(Toolbar, {
      props: { editor: makeEditor(calls), fullscreen: false },
      global: { plugins: [i18n] },
    })
    await wrapper.find('button[aria-label="editor.fullscreen"]').trigger('click')
    expect(wrapper.emitted('toggle-fullscreen')).toBeTruthy()
  })

  it('toggleHorizontalRule click triggers setHorizontalRule', async () => {
    const { default: Toolbar } = await import('../../src/components/editor/toolbar/RichEditorToolbar.vue')
    const wrapper = mount(Toolbar, {
      props: { editor: makeEditor(calls) },
      global: { plugins: [i18n] },
    })
    await wrapper.find('button[aria-label="editor.horizontal_rule"]').trigger('click')
    expect(calls).toContain('setHorizontalRule')
  })
})
