import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowRef } from 'vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'en' } }),
}))

const messageMock = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }
vi.mock('naive-ui', () => ({
  useMessage: () => messageMock,
}))

import { useEditorVideoDialog } from '@/components/editor/useEditorVideoDialog'
import { useEditorDetailsDialog } from '@/components/editor/useEditorDetailsDialog'
import { buildEditorExtensions } from '@/components/editor/extensions'
// Редактор берётся из @tiptap/vue-3 (не core): у vue-3 свой класс Editor
// с реактивным состоянием, и именно его ждут композаблы диалогов.
import { Editor } from '@tiptap/vue-3'

interface ChainRecord {
  calls: Array<[string, ...unknown[]]>
}

function makeChain(record: ChainRecord) {
  const handler: ProxyHandler<Record<string, unknown>> = {
    get(_t, prop: string) {
      if (prop === 'run') return () => true
      if (prop === 'command') {
        return (fn: (p: { tr: unknown }) => boolean) => {
          record.calls.push(['command'])
          fn({ tr: { setNodeMarkup: (...a: unknown[]) => record.calls.push(['setNodeMarkup', ...a]) } })
          return proxy
        }
      }
      return (...args: unknown[]) => {
        record.calls.push([prop, ...args])
        return proxy
      }
    },
  }
  const proxy = new Proxy({}, handler)
  return proxy
}

describe('useEditorVideoDialog (конвертация через общий парсер)', () => {
  beforeEach(() => {
    messageMock.error.mockReset()
  })

  function makeDialog(origins?: () => string[]) {
    const setIframe = vi.fn(() => true)
    const editor = shallowRef<Editor | undefined>({ commands: { setIframe } } as unknown as Editor)
    const v = useEditorVideoDialog(editor, origins)
    return { v, setIframe }
  }

  it('insertVideo: embed-код → извлекается src и конвертируется в канонический embed', () => {
    const { v, setIframe } = makeDialog()
    v.videoUrl.value = '<iframe src="https://youtube.com/embed/abc"></iframe>'
    v.insertVideo()
    // youtube.com/embed конвертируется в youtube-nocookie (embed-origin из CSP)
    expect(setIframe).toHaveBeenCalledWith({
      src: 'https://www.youtube-nocookie.com/embed/abc',
      title: '',
    })
    expect(v.showVideoDialog.value).toBe(false)
    expect(v.videoUrl.value).toBe('')
  })

  it('insertVideo: обычная ссылка → embed-адрес провайдера', () => {
    const { v, setIframe } = makeDialog()
    v.videoUrl.value = '  https://vimeo.com/123  '
    v.insertVideo()
    expect(setIframe).toHaveBeenCalledWith({
      src: 'https://player.vimeo.com/video/123',
      title: '',
    })
  })

  it('insertVideo: PeerTube (video.mage.ru) watch-ссылка → embed-путь', () => {
    const { v, setIframe } = makeDialog()
    v.videoUrl.value = 'https://video.mage.ru/w/9vqBpmmUiwkrqFwLfpnH8i'
    v.insertVideo()
    expect(setIframe).toHaveBeenCalledWith({
      src: 'https://video.mage.ru/videos/embed/9vqBpmmUiwkrqFwLfpnH8i',
      title: '',
    })
  })

  it('insertVideo: готовый PeerTube embed-код — src без изменений', () => {
    const { v, setIframe } = makeDialog()
    v.videoUrl.value =
      '<iframe src="https://video.mage.ru/videos/embed/44e4d865-ad2e-4702-b5cc-0d64f8dd1de3" allowfullscreen></iframe>'
    v.insertVideo()
    expect(setIframe).toHaveBeenCalledWith({
      src: 'https://video.mage.ru/videos/embed/44e4d865-ad2e-4702-b5cc-0d64f8dd1de3',
      title: '',
    })
  })

  it('insertVideo: пустой ввод — no-op', () => {
    const { v, setIframe } = makeDialog()
    v.videoUrl.value = '   '
    v.insertVideo()
    expect(setIframe).not.toHaveBeenCalled()
  })

  it('insertVideo: не-видео — ошибка, вставки нет, диалог открыт', () => {
    const { v, setIframe } = makeDialog()
    v.showVideoDialog.value = true
    v.videoUrl.value = 'not-a-video'
    v.insertVideo()
    expect(messageMock.error).toHaveBeenCalledWith('editor.invalidVideoUrl')
    expect(setIframe).not.toHaveBeenCalled()
    expect(v.showVideoDialog.value).toBe(true)
  })

  it('insertVideo: origin вне списка настройки — отклонён (гейт = CSP)', () => {
    const { v, setIframe } = makeDialog(() => ['https://video.mage.ru'])
    v.videoUrl.value = 'https://rutube.ru/video/abc123def0/'
    v.insertVideo()
    expect(messageMock.error).toHaveBeenCalledWith('editor.invalidVideoUrl')
    expect(setIframe).not.toHaveBeenCalled()
  })

  it('insertVideo: список настройки читается в момент вставки (живой гейт)', () => {
    const origins = vi.fn(() => ['https://video.mage.ru', 'https://rutube.ru'])
    const { v, setIframe } = makeDialog(origins)
    v.videoUrl.value = 'https://rutube.ru/video/abc123def0/'
    v.insertVideo()
    expect(setIframe).toHaveBeenCalledWith({
      src: 'https://rutube.ru/play/embed/abc123def0',
      title: '',
    })
    expect(origins).toHaveBeenCalled()
  })
})

describe('IframeEmbed: markdown-циркуляция (сохранение → открытие)', () => {
  it('setIframe попадает в markdown; обратный парс восстанавливает узел', () => {
    const editor = new Editor({ extensions: buildEditorExtensions() })
    editor.commands.setContent('<p>Видео:</p>')
    expect(
      editor.commands.setIframe({
        src: 'https://video.mage.ru/videos/embed/9vqBpmmUiwkrqFwLfpnH8i',
        title: '',
      }),
    ).toBe(true)

    const markdown = (editor.storage as any).markdown.getMarkdown()
    expect(markdown).toContain('<iframe src="https://video.mage.ru/videos/embed/9vqBpmmUiwkrqFwLfpnH8i"')
    expect(markdown).toContain('sandbox=')

    // Регресс: раньше узел без markdown-сериализатора молча выпадал при
    // сохранении — тело новости сохранялось без видео.
    const reopened = new Editor({ extensions: buildEditorExtensions(), content: markdown })
    const json = JSON.stringify(reopened.getJSON())
    expect(json).toContain('iframeEmbed')
    expect(json).toContain('videos/embed/9vqBpmmUiwkrqFwLfpnH8i')
    editor.destroy()
    reopened.destroy()
  })

  it('самолечение: legacy watch-iframe конвертируется в embed при открытии', () => {
    const legacy = '<p>Видео:</p><iframe src="https://video.mage.ru/w/oqiQGxn9m9ygf4mkK6Rosv" title="" width="100%" height="360"></iframe>'
    const editor = new Editor({ extensions: buildEditorExtensions(), content: legacy })
    const json = JSON.stringify(editor.getJSON())
    // src узла уже исправлен при разборе — сохранение запишет embed в БД
    expect(json).toContain('videos/embed/oqiQGxn9m9ygf4mkK6Rosv')
    expect(json).not.toContain('/w/oqiQGxn9m9ygf4mkK6Rosv')
    editor.destroy()
  })

  it('самолечение уважает настроенный список origin (configure доезжает до атрибута)', () => {
    const legacy = '<p>Видео:</p><iframe src="https://rutube.ru/video/abc123def0/"></iframe>'
    const editor = new Editor({
      extensions: buildEditorExtensions('', ['https://rutube.ru']),
      content: legacy,
    })
    const json = JSON.stringify(editor.getJSON())
    expect(json).toContain('rutube.ru/play/embed/abc123def0')
    editor.destroy()
  })
})

describe('useEditorDetailsDialog (RE-0 characterizing)', () => {
  it('openDetailsDialog: clears summary and opens', () => {
    const editor = shallowRef<Editor | undefined>(undefined)
    const d = useEditorDetailsDialog(editor)
    d.detailsSummary.value = 'old'
    d.openDetailsDialog()
    expect(d.detailsSummary.value).toBe('')
    expect(d.showDetailsDialog.value).toBe(true)
  })

  it('insertDetails: inserts trimmed summary and closes', () => {
    const record: ChainRecord = { calls: [] }
    const editor = shallowRef<Editor | undefined>({ chain: () => makeChain(record) } as unknown as Editor)
    const d = useEditorDetailsDialog(editor)
    d.detailsSummary.value = '  Spoiler  '
    d.showDetailsDialog.value = true
    d.insertDetails()
    const insert = record.calls.find((c) => c[0] === 'insertDetails')
    expect(insert).toEqual(['insertDetails', 'Spoiler'])
    expect(d.showDetailsDialog.value).toBe(false)
    expect(d.detailsSummary.value).toBe('')
  })

  it('preventDetailsToggle: no summary ancestor is a no-op', () => {
    const editor = shallowRef<Editor | undefined>(undefined)
    const d = useEditorDetailsDialog(editor)
    const preventDefault = vi.fn()
    d.preventDetailsToggle({ target: { closest: () => null }, preventDefault } as unknown as MouseEvent)
    expect(preventDefault).not.toHaveBeenCalled()
  })

  it('preventDetailsToggle: summary without details element is a no-op', () => {
    const editor = shallowRef<Editor | undefined>(undefined)
    const d = useEditorDetailsDialog(editor)
    const preventDefault = vi.fn()
    const summary = { closest: () => null }
    const target = { closest: (sel: string) => (sel === 'summary' ? summary : null) }
    d.preventDetailsToggle({ target, preventDefault } as unknown as MouseEvent)
    expect(preventDefault).not.toHaveBeenCalled()
  })

  it('preventDetailsToggle: toggles open attribute of details node', () => {
    const record: ChainRecord = { calls: [] }
    const detailsEl = {}
    const summary = { closest: () => detailsEl }
    const target = { closest: (sel: string) => (sel === 'summary' ? summary : null) }

    const node = { type: { name: 'details' }, attrs: { open: false } }
    const resolved = {
      depth: 1,
      node: (_d: number) => node,
      before: (_d: number) => 5,
    }
    const editor = shallowRef<Editor | undefined>({
      view: { posAtDOM: () => 5 },
      state: { doc: { resolve: () => resolved } },
      chain: () => makeChain(record),
    } as unknown as Editor)

    const d = useEditorDetailsDialog(editor)
    const preventDefault = vi.fn()
    d.preventDetailsToggle({ target, preventDefault } as unknown as MouseEvent)
    expect(preventDefault).toHaveBeenCalled()
    const setMarkup = record.calls.find((c) => c[0] === 'setNodeMarkup')
    expect(setMarkup).toBeTruthy()
    expect(setMarkup![3]).toEqual({ open: true })
  })
})
