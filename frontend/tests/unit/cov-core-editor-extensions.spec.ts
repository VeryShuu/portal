import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@tiptap/core', async () => {
  const actual = await vi.importActual<any>('@tiptap/core')
  return {
    ...actual,
    getHTMLFromFragment: vi.fn(() => '<p>inner</p>'),
  }
})

describe('src/components/editor/extensions/Details', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('attributes parse/render and parseHTML contentElement branches', async () => {
    const { Details } = await import('../../src/components/editor/extensions/Details')
    const attrs = (Details as any).config.addAttributes()

    const el = document.createElement('details')
    el.setAttribute('open', '')
    const summary = document.createElement('summary')
    summary.textContent = 'Summary text'
    const body = document.createElement('div')
    body.className = 'details-content'
    body.textContent = 'Body'
    el.append(summary, body)

    expect(attrs.summary.parseHTML(el)).toBe('Summary text')
    expect(attrs.open.parseHTML(el)).toBe(true)
    expect(attrs.open.renderHTML({ open: true })).toEqual({ open: '' })
    expect(attrs.open.renderHTML({ open: false })).toEqual({})

    const parseDef = (Details as any).config.parseHTML()[0]
    expect(parseDef.getAttrs(el)).toEqual({ summary: 'Summary text', open: true })
    expect(parseDef.contentElement(el)).toBe(body)

    const elNoWrapper = document.createElement('details')
    const summary2 = document.createElement('summary')
    summary2.textContent = 'S2'
    const p = document.createElement('p')
    p.textContent = 'Paragraph'
    elNoWrapper.append(summary2, p)

    const fallback = parseDef.contentElement(elNoWrapper)
    expect((fallback as HTMLElement).querySelector('summary')).toBeNull()
    expect((fallback as HTMLElement).textContent).toContain('Paragraph')
  })

  it('renderHTML outputs details with summary and content wrapper', async () => {
    const { Details } = await import('../../src/components/editor/extensions/Details')
    const out = (Details as any).config.renderHTML({
      node: { attrs: { summary: 'Spoiler' } },
      HTMLAttributes: { class: 'x' },
    })

    expect(out[0]).toBe('details')
    expect(out[2]).toEqual(['summary', {}, 'Spoiler'])
    expect(out[3]).toEqual(['div', { class: 'details-content' }, 0])
  })

  it('insertDetails command covers default, block selection, and text selection branches', async () => {
    const { Details } = await import('../../src/components/editor/extensions/Details')

    const chainCtx: any = {
      inserted: null,
      runResult: true,
      chain() {
        return {
          focus: () => ({
            insertContent: (payload: any) => ({
              run: () => {
                chainCtx.inserted = payload
                return chainCtx.runResult
              },
            }),
          }),
        }
      },
    }

    const selectionState = {
      selection: {
        from: 1,
        to: 1,
        content: () => ({ content: { toJSON: () => [] } }),
      },
      doc: {
        textBetween: vi.fn(() => ''),
      },
    }

    const setTextSelection = vi.fn()
    const detailsNode = {
      type: { name: 'details' },
      descendants: (cb: any) => {
        cb({ isTextblock: true, nodeSize: 6 }, 3)
      },
    }

    const makeResolvedPos = () => ({
      depth: 1,
      node: (d: number) => (d === 1 ? detailsNode : { type: { name: 'doc' } }),
      before: () => 5,
    })

    const ctx: any = {
      name: 'details',
      editor: {
        state: {
          tr: {
            selection: { from: 10 },
            doc: {
              resolve: makeResolvedPos,
            },
          },
        },
        commands: { setTextSelection },
      },
    }

    const commands = (Details as any).config.addCommands.call(ctx)

    const resultDefault = commands.insertDetails('S1')({ state: selectionState, chain: chainCtx.chain })
    expect(resultDefault).toBe(true)
    expect(chainCtx.inserted).toEqual({
      type: 'details',
      attrs: { summary: 'S1', open: true },
      content: [{ type: 'paragraph' }],
    })

    chainCtx.inserted = null
    const blockState = {
      selection: {
        from: 1,
        to: 5,
        content: () => ({
          content: {
            toJSON: () => [{ type: 'paragraph' }, { type: 'heading' }],
          },
        }),
      },
      doc: { textBetween: vi.fn(() => '') },
    }
    commands.insertDetails('S2')({ state: blockState, chain: chainCtx.chain })
    expect(chainCtx.inserted.content).toEqual([{ type: 'paragraph' }, { type: 'heading' }])

    chainCtx.inserted = null
    const textState = {
      selection: {
        from: 1,
        to: 5,
        content: () => ({
          content: {
            toJSON: () => [{ type: 'text', text: 'abc' }],
          },
        }),
      },
      doc: { textBetween: vi.fn(() => 'line1\nline2') },
    }
    commands.insertDetails('S3')({ state: textState, chain: chainCtx.chain })
    expect(chainCtx.inserted.content).toEqual([
      { type: 'paragraph', content: [{ type: 'text', text: 'line1' }] },
      { type: 'paragraph', content: [{ type: 'text', text: 'line2' }] },
    ])
  })

  it('markdown serialize escapes summary and writes details block', async () => {
    const { Details } = await import('../../src/components/editor/extensions/Details')
    const storage = (Details as any).config.addStorage()
    const writes: string[] = []
    const state = {
      write: (s: string) => writes.push(s),
      ensureNewLine: vi.fn(),
      closeBlock: vi.fn(),
    }

    storage.markdown.serialize(state, {
      attrs: { summary: ' A <&> "B" ' },
      type: { schema: {} },
      content: [],
    })

    expect(writes[0]).toBe('<details>')
    expect(writes[1]).toBe('<summary>A &lt;&amp;&gt; &quot;B&quot;</summary>')
    expect(writes[3]).toBe('<p>inner</p>')
    expect(writes[4]).toBe('</details>')
    expect(state.closeBlock).toHaveBeenCalled()
  })
})

describe('src/components/editor/extensions/FigureImage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('attributes parse from img/figure and parseHTML config', async () => {
    const { FigureImage } = await import('../../src/components/editor/extensions/FigureImage')
    const attrs = (FigureImage as any).config.addAttributes()

    const img = document.createElement('img')
    img.setAttribute('src', '/a.png')
    img.setAttribute('alt', 'Alt')
    img.setAttribute('title', 'Title')

    const fig = document.createElement('figure')
    const img2 = document.createElement('img')
    img2.setAttribute('src', '/b.png')
    img2.setAttribute('alt', 'Alt2')
    const cap = document.createElement('figcaption')
    cap.textContent = ' Caption '
    fig.append(img2, cap)

    expect(attrs.src.parseHTML(img)).toBe('/a.png')
    expect(attrs.alt.parseHTML(img)).toBe('Alt')
    expect(attrs.title.parseHTML(img)).toBe('Title')
    expect(attrs.caption.parseHTML(img)).toBe('')

    expect(attrs.src.parseHTML(fig)).toBe('/b.png')
    expect(attrs.alt.parseHTML(fig)).toBe('Alt2')
    expect(attrs.caption.parseHTML(fig)).toBe('Caption')

    const parseDefs = (FigureImage as any).config.parseHTML()
    expect(parseDefs).toEqual([
      { tag: 'figure', priority: 60 },
      { tag: 'img[src]', priority: 50 },
    ])
  })

  it('renderHTML includes figcaption only when non-empty', async () => {
    const { FigureImage } = await import('../../src/components/editor/extensions/FigureImage')

    const withCaption = (FigureImage as any).config.renderHTML({
      node: { attrs: { src: '/x.png', alt: 'A', title: 'T', caption: 'Cap' } },
      HTMLAttributes: { class: 'img' },
    })
    expect(withCaption[0]).toBe('figure')
    expect((withCaption as any[]).some((c) => Array.isArray(c) && c[0] === 'figcaption')).toBe(true)

    const withoutCaption = (FigureImage as any).config.renderHTML({
      node: { attrs: { src: '/x.png', alt: 'A', title: 'T', caption: '   ' } },
      HTMLAttributes: {},
    })
    expect((withoutCaption as any[]).some((c) => Array.isArray(c) && c[0] === 'figcaption')).toBe(false)
  })

  it('commands setFigureImage/updateFigureImage call insert/updateAttributes', async () => {
    const { FigureImage } = await import('../../src/components/editor/extensions/FigureImage')
    const ctx: any = { name: 'figureImage' }
    const commands = (FigureImage as any).config.addCommands.call(ctx)

    const insertContent = vi.fn().mockReturnValue(true)
    const updateAttributes = vi.fn().mockReturnValue(true)

    commands.setFigureImage({ src: '/x.png' })({ commands: { insertContent } })
    expect(insertContent).toHaveBeenCalledWith({
      type: 'figureImage',
      attrs: { src: '/x.png', alt: '', title: '', caption: '' },
    })

    commands.updateFigureImage({ caption: 'C' })({ commands: { updateAttributes } })
    expect(updateAttributes).toHaveBeenCalledWith('figureImage', { caption: 'C' })
  })

  it('markdown serialize handles markdown branch and figure html branch with escaping', async () => {
    const { FigureImage } = await import('../../src/components/editor/extensions/FigureImage')
    const storage = (FigureImage as any).config.addStorage()

    const writes1: string[] = []
    const state1 = {
      write: (s: string) => writes1.push(s),
      ensureNewLine: vi.fn(),
      closeBlock: vi.fn(),
    }

    storage.markdown.serialize(state1, {
      attrs: { src: '/a.png', alt: 'Alt', title: 'Ti"tle', caption: '  ' },
    })
    expect(writes1[0]).toBe('![Alt](/a.png "Ti\\"tle")')
    expect(state1.closeBlock).toHaveBeenCalled()

    const writes2: string[] = []
    const state2 = {
      write: (s: string) => writes2.push(s),
      ensureNewLine: vi.fn(),
      closeBlock: vi.fn(),
    }

    storage.markdown.serialize(state2, {
      attrs: {
        src: '/a.png?x=1&y=2',
        alt: `A ' < > &`,
        title: `T ' < > &`,
        caption: ` C <&> "Q" `,
      },
    })

    expect(writes2[0]).toBe('<figure data-type="figure-image">')
    expect(writes2[1]).toContain('src="/a.png?x=1&amp;y=2"')
    expect(writes2[1]).toContain('alt="A &#39; &lt; &gt; &amp;"')
    expect(writes2[1]).toContain('title="T &#39; &lt; &gt; &amp;"')
    expect(writes2[2]).toBe('<figcaption>C &lt;&amp;&gt; &quot;Q&quot;</figcaption>')
    expect(writes2[3]).toBe('</figure>')
  })
})
