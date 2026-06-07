import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { h } from 'vue'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const fileApiMock = vi.hoisted(() => ({
  downloadFile: vi.fn((folderId: string, name: string) => `/dl/${folderId}/${name}`),
  fileIcon: vi.fn(() => ({ kind: 'emoji', char: '📎' })),
  formatFileSize: vi.fn((n: number) => `${n}b`),
  isCollaboraFile: vi.fn(() => false),
  isPreviewableImage: vi.fn(() => false),
  isPreviewablePdf: vi.fn(() => false),
}))

const storeMock = vi.hoisted(() => ({
  load: vi.fn(),
  iconUrlFor: vi.fn(() => null),
}))

vi.mock('naive-ui', () => ({
  NButton: {
    name: 'NButton',
    template: '<button class="n-button" @click="$emit(\'click\', $event)"><slot /></button>',
    props: ['size', 'type', 'disabled', 'loading', 'ghost', 'quaternary', 'tertiary', 'circle', 'title', 'tag', 'href', 'download', 'text'],
    emits: ['click'],
  },
  NDropdown: {
    name: 'NDropdown',
    template: '<div class="n-dropdown"><slot /><button v-for="o in options" :key="o.key" class="dd-opt" @click="$emit(\'select\', o.key)">{{ String(o.key) }}</button></div>',
    props: ['trigger', 'options'],
    emits: ['select'],
  },
  NDataTable: {
    name: 'NDataTable',
    template: '<div class="n-data-table" />',
    props: ['columns', 'data', 'rowKey', 'checkedRowKeys', 'rowProps', 'size', 'bordered', 'singleLine'],
    emits: ['update:checked-row-keys'],
  },
  NTooltip: {
    name: 'NTooltip',
    template: '<div class="n-tooltip"><slot name="trigger" /><slot /></div>',
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('../../src/api/files', () => fileApiMock)
vi.mock('../../src/stores/fileIcons', () => ({
  useFileIconsStore: () => storeMock,
}))
vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

function globalMountOptions() {
  return {
    global: {
      plugins: [i18n],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  }
}

function makeItem(overrides: Record<string, unknown> = {}) {
  return {
    name: 'doc.txt',
    nc_path: '/doc.txt',
    is_dir: false,
    size_bytes: 128,
    mime_type: 'text/plain',
    last_modified: '2024-01-01T10:00:00Z',
    etag: 'e',
    uploaded_at: '2024-01-01T11:00:00Z',
    uploaded_by: { id: 'u1', full_name: 'User Name', avatar_url: null },
    ...overrides,
  }
}

function makeTreeNode(overrides: Record<string, unknown> = {}) {
  return {
    id: 'root',
    parent_id: null,
    name: 'Root',
    nc_path: '/Root',
    permission: 'manager',
    inherit_permissions: true,
    children: [],
    ...overrides,
  }
}

describe('FilesTable', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  async function mountTable(props: Record<string, unknown> = {}) {
    const { default: Comp } = await import('../../src/components/files/FilesTable.vue')
    return mount(Comp, {
      ...globalMountOptions(),
      props: {
        items: [makeItem()],
        loading: false,
        selectedKeys: [],
        canUpload: true,
        canEdit: true,
        canManage: true,
        folderId: 'fold-1',
        openingCollaboraFile: null,
        ...props,
      },
    })
  }

  it('mounts and loads icon store on mounted', async () => {
    const wrapper = await mountTable()
    expect(wrapper.exists()).toBe(true)
    expect(storeMock.load).toHaveBeenCalledTimes(1)
  })

  it('builds name cell with svg icon branch and emoji branch', async () => {
    fileApiMock.fileIcon.mockReturnValueOnce({ kind: 'svg', url: '/x.svg', alt: 'TXT' })
    const wrapper = await mountTable()
    const dt = wrapper.findComponent({ name: 'NDataTable' })
    const columns = dt.props('columns') as Array<Record<string, any>>
    const nameCol = columns.find((c) => c.key === 'name')!

    const svgVnode = nameCol.render(makeItem({ name: 'a.txt' }))
    const svgIcon = (svgVnode.children as any[])[0]
    expect(svgIcon.type).toBe('img')

    fileApiMock.fileIcon.mockReturnValueOnce({ kind: 'emoji', char: '📄' })
    const emojiVnode = nameCol.render(makeItem({ name: 'b.txt' }))
    const emojiIcon = (emojiVnode.children as any[])[0]
    expect(emojiIcon.type).toBe('span')
  })

  it('renders uploaded column with tooltip only when uploaded_by exists', async () => {
    const wrapper = await mountTable()
    const dt = wrapper.findComponent({ name: 'NDataTable' })
    const columns = dt.props('columns') as Array<Record<string, any>>
    const uploadedCol = columns.find((c) => c.key === 'uploaded_at')!

    const withUser = uploadedCol.render(makeItem())
    expect(withUser.type.name).toBe('NTooltip')

    const noUser = uploadedCol.render(makeItem({ uploaded_by: null }))
    expect(typeof noUser).toBe('string')
  })

  it('builds action buttons and emits for preview/share/delete/open-collabora', async () => {
    fileApiMock.isPreviewableImage.mockImplementation((row: any) => row.name.endsWith('.png'))
    fileApiMock.isPreviewablePdf.mockImplementation((row: any) => row.name.endsWith('.pdf'))
    fileApiMock.isCollaboraFile.mockImplementation((row: any) => row.name.endsWith('.docx'))

    const wrapper = await mountTable({ canUpload: true, canManage: true, canEdit: true })
    const dt = wrapper.findComponent({ name: 'NDataTable' })
    const columns = dt.props('columns') as Array<Record<string, any>>
    const actionsCol = columns.find((c) => c.key === 'actions')!

    const image = makeItem({ name: 'img.png', mime_type: 'image/png' })
    const imageButtons = (actionsCol.render(image).children as any[])
    ;(imageButtons[0].props.onClick as (...args: any[]) => any)({ stopPropagation: vi.fn() })
    ;(imageButtons[2].props.onClick as (...args: any[]) => any)({ stopPropagation: vi.fn() })
    ;(imageButtons[3].props.onClick as (...args: any[]) => any)({ stopPropagation: vi.fn() })
    expect(wrapper.emitted('preview-image')).toBeTruthy()
    expect(wrapper.emitted('share-file')).toBeTruthy()
    expect(wrapper.emitted('delete-file')).toBeTruthy()

    const pdf = makeItem({ name: 'f.pdf', mime_type: 'application/pdf' })
    const pdfButtons = (actionsCol.render(pdf).children as any[])
    ;(pdfButtons[0].props.onClick as (...args: any[]) => any)({ stopPropagation: vi.fn() })
    expect(wrapper.emitted('preview-pdf')).toBeTruthy()

    const collab = makeItem({ name: 'a.docx', mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const collabButtons = (actionsCol.render(collab).children as any[])
    ;(collabButtons[1].props.onClick as (...args: any[]) => any)({ stopPropagation: vi.fn() })
    expect(wrapper.emitted('open-collabora')).toBeTruthy()
  })

  it('uses fallback download url when folderId is null', async () => {
    const wrapper = await mountTable({ folderId: null, canManage: false, canUpload: false })
    const dt = wrapper.findComponent({ name: 'NDataTable' })
    const columns = dt.props('columns') as Array<Record<string, any>>
    const actionsCol = columns.find((c) => c.key === 'actions')!
    fileApiMock.isPreviewableImage.mockReturnValueOnce(false)
    fileApiMock.isPreviewablePdf.mockReturnValueOnce(false)
    fileApiMock.isCollaboraFile.mockReturnValueOnce(false)
    const btns = actionsCol.render(makeItem({ name: 'x.txt' })).children as any[]
    expect(btns[0].props.href).toBe('#')
  })

  it('rowProps emits row-click and marks directories with class', async () => {
    const dir = makeItem({ is_dir: true, name: 'Dir' })
    const wrapper = await mountTable({ items: [dir] })
    const dt = wrapper.findComponent({ name: 'NDataTable' })
    const rowProps = dt.props('rowProps') as (...args: any[]) => any
    const props = rowProps(dir, 0)
    expect(props.class).toBe('files-row--dir')
    props.onClick({ stopPropagation: vi.fn() })
    expect(wrapper.emitted('row-click')).toBeTruthy()
  })
})

describe('FileFolderNode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  async function mountNode(props: Record<string, unknown> = {}) {
    const { default: Comp } = await import('../../src/components/FileFolderNode.vue')
    return mount(Comp, {
      ...globalMountOptions(),
      props: {
        node: makeTreeNode({ children: [makeTreeNode({ id: 'child-1', name: 'Child', children: [] })] }),
        selectedId: null,
        ...props,
      },
    })
  }

  it('mounts and emits select on row click and enter key', async () => {
    const wrapper = await mountNode()
    expect(wrapper.exists()).toBe(true)
    const row = wrapper.find('.ff-node__row')
    await row.trigger('click')
    await row.trigger('keydown.enter')
    expect(wrapper.emitted('select')?.length).toBe(2)
  })

  it('toggles expanded state and hides children for nodes with children', async () => {
    const wrapper = await mountNode()
    expect(wrapper.find('.ff-node__children').exists()).toBe(true)
    await wrapper.find('.ff-node__toggle').trigger('click')
    expect(wrapper.find('.ff-node__children').exists()).toBe(false)
  })

  it('shows no menu options for viewer permission', async () => {
    const wrapper = await mountNode({ node: makeTreeNode({ permission: 'viewer', children: [] }) })
    expect(wrapper.findAll('.dd-opt')).toHaveLength(0)
  })

  it('emits create-child for editor and manage/delete for manager', async () => {
    const editorWrapper = await mountNode({ node: makeTreeNode({ permission: 'editor', children: [] }) })
    const editorOpts = editorWrapper.findAll('.dd-opt')
    expect(editorOpts.map((b) => b.text())).toContain('create-child')
    await editorOpts[0].trigger('click')
    expect(editorWrapper.emitted('create-child')).toBeTruthy()

    const managerWrapper = await mountNode({ node: makeTreeNode({ permission: 'manager', children: [] }) })
    const managerOpts = managerWrapper.findAll('.dd-opt')
    expect(managerOpts.map((b) => b.text())).toEqual(['create-child', 'manage', 'delete'])
    await managerOpts[1].trigger('click')
    await managerOpts[2].trigger('click')
    expect(managerWrapper.emitted('manage')).toBeTruthy()
    expect(managerWrapper.emitted('delete')).toBeTruthy()
  })
})
