import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('naive-ui', () => ({
  NButton: 'NButton',
  NIcon: 'NIcon',
  NTag: 'NTag',
}))
vi.mock('@vicons/ionicons5', () => ({
  CreateOutline: 'CreateOutline',
  TrashOutline: 'TrashOutline',
  ShieldCheckmarkOutline: 'ShieldCheckmarkOutline',
  HomeOutline: 'HomeOutline',
}))

function makeLink(overrides: Record<string, unknown> = {}) {
  return {
    id: 'l-1',
    title: 'Portal',
    url: 'https://portal.test',
    icon_url: null,
    description: null,
    category: 'Work',
    sort_order: 1,
    supports_sso: true,
    is_active: true,
    show_on_home: true,
    kb_url: null,
    created_at: '',
    updated_at: '',
    ...overrides,
  }
}

describe('useLinkColumns', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns 8 columns with expected keys', async () => {
    const { useLinkColumns } = await import('../../src/composables/useLinkColumns')
    const { linkColumns } = useLinkColumns(vi.fn(), vi.fn())
    const cols = linkColumns.value
    expect(cols).toHaveLength(8)
    expect(cols.map((c: any) => c.key)).toEqual([
      'icon', 'title', 'url', 'category', 'supports_sso', 'is_active', 'show_on_home', 'actions',
    ])
  })

  it('icon column renders img when icon_url present, null otherwise', async () => {
    const { useLinkColumns } = await import('../../src/composables/useLinkColumns')
    const { linkColumns } = useLinkColumns(vi.fn(), vi.fn())
    const iconCol = (linkColumns.value as any[]).find((c) => c.key === 'icon')
    expect(iconCol.render(makeLink({ icon_url: '/i.png' }))).toMatchObject({ type: 'img' })
    expect(iconCol.render(makeLink({ icon_url: null }))).toBeNull()
  })

  it('is_active column renders NTag', async () => {
    const { useLinkColumns } = await import('../../src/composables/useLinkColumns')
    const { linkColumns } = useLinkColumns(vi.fn(), vi.fn())
    const activeCol = (linkColumns.value as any[]).find((c) => c.key === 'is_active')
    const node = activeCol.render(makeLink({ is_active: true }))
    expect(node).toMatchObject({ type: 'NTag' })
  })

  it('actions column calls onEdit and onDelete callbacks', async () => {
    const { useLinkColumns } = await import('../../src/composables/useLinkColumns')
    const onEdit = vi.fn()
    const onDelete = vi.fn()
    const { linkColumns } = useLinkColumns(onEdit, onDelete)
    const actionsCol = (linkColumns.value as any[]).find((c) => c.key === 'actions')
    const link = makeLink()

    // render returns a div-vnode with two NButton children; onClick lives on each button props.
    const vnode = actionsCol.render(link)
    expect(vnode.type).toBe('div')
    const buttons = vnode.children
    expect(buttons).toHaveLength(2)
    buttons[0].props.onClick()
    buttons[1].props.onClick()
    expect(onEdit).toHaveBeenCalledWith(link)
    expect(onDelete).toHaveBeenCalledWith(link)
  })
})
