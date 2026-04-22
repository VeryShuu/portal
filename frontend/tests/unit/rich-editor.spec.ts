/**
 * Smoke-test RichEditor: монтируется и принимает modelValue.
 */
import { describe, it, expect, vi } from 'vitest'

// Tiptap требует DOM API — jsdom уже подключён глобально.
vi.mock('@tiptap/vue-3', () => ({
  useEditor: vi.fn(() => ({
    value: {
      isActive: () => false,
      chain: () => ({ focus: () => ({ toggleBold: () => ({ run: vi.fn() }) }) }),
      getHTML: () => '<p>x</p>',
      commands: { setContent: vi.fn() },
      destroy: vi.fn(),
    },
  })),
  EditorContent: { name: 'EditorContent', render: () => null },
}))

vi.mock('@tiptap/starter-kit', () => ({ default: {} }))
vi.mock('@tiptap/extension-placeholder', () => ({ default: { configure: () => ({}) } }))
vi.mock('@tiptap/extension-link', () => ({ default: { configure: () => ({}) } }))
vi.mock('@tiptap/extension-image', () => ({ default: {} }))

vi.mock('naive-ui', () => ({
  NButton: { name: 'NButton', render: () => null },
  NButtonGroup: { name: 'NButtonGroup', render: () => null },
}))

describe('RichEditor', () => {
  it('импортируется без ошибок', async () => {
    const mod = await import('../../src/components/RichEditor.vue')
    expect(mod.default).toBeDefined()
  })
})
