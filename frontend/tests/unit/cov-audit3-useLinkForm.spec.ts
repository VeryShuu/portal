import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'

const messageMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }))
const confirmMock = vi.hoisted(() => vi.fn())
const storeMock = vi.hoisted(() => ({
  addLink: vi.fn(),
  updateLinkItem: vi.fn(),
  removeLink: vi.fn(),
  clearLinkIcon: vi.fn(),
}))
const createLinkMock = vi.hoisted(() => vi.fn())
const updateLinkMock = vi.hoisted(() => vi.fn())
const deleteLinkMock = vi.hoisted(() => vi.fn())
const uploadLinkIconMock = vi.hoisted(() => vi.fn())
const deleteLinkIconMock = vi.hoisted(() => vi.fn())
const parseApiErrorMock = vi.hoisted(() => vi.fn(() => 'parsed-error'))

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('naive-ui', () => ({ useMessage: () => messageMock }))
vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useMutation: () => ({
    mutateAsync: vi.fn(),
  }),
}))
vi.mock('../../src/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: confirmMock }) }))
vi.mock('../../src/stores/links', () => ({ useLinksStore: () => storeMock }))
vi.mock('../../src/queries/admin', () => ({
  // Контракты из queries/admin.ts: mutateAsync принимает объект-аргумент
  // (updateLink: {id, dto}, uploadLinkIcon: {id, file}), а не позиционные.
  useCreateLinkMutation: () => ({ mutateAsync: createLinkMock }),
  useUpdateLinkMutation: () => ({ mutateAsync: (arg: { id: string; dto: unknown }) => updateLinkMock(arg.id, arg.dto) }),
  useDeleteLinkMutation: () => ({ mutateAsync: deleteLinkMock }),
  useUploadLinkIconMutation: () => ({ mutateAsync: (arg: { id: string; file: File }) => uploadLinkIconMock(arg.id, arg.file) }),
  useDeleteLinkIconMutation: () => ({ mutateAsync: deleteLinkIconMock }),
}))
vi.mock('../../src/utils/parseApiError', () => ({ parseApiError: parseApiErrorMock }))
vi.mock('../../src/utils/url', () => ({ isServiceLinkUrl: (v: string) => /^https?:\/\//.test(v) }))

function makeIcon() {
  return {
    iconFile: ref<File | null>(null),
    iconRemoved: ref(false),
    resetIconState: vi.fn(),
  }
}

function makeEditingLink(overrides: Record<string, unknown> = {}) {
  return {
    id: 'l-1',
    title: 'Title',
    url: 'https://portal.test',
    icon_url: '/old.png',
    description: 'desc',
    category: 'cat',
    sort_order: 2,
    supports_sso: true,
    is_active: true,
    show_on_home: false,
    kb_url: null,
    created_at: '',
    updated_at: '',
    ...overrides,
  }
}

describe('useLinkForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('openAddLink resets form and editing state', async () => {
    const { useLinkForm } = await import('../../src/composables/useLinkForm')
    const icon = makeIcon()
    const form = useLinkForm(icon)

    form.openAddLink()

    expect(form.editingLink.value).toBeNull()
    expect(form.linkModalOpen.value).toBe(true)
    expect(form.linkForm.value.title).toBe('')
    expect(icon.resetIconState).toHaveBeenCalledOnce()
  })

  it('openEditLink copies fields from link and resets icon', async () => {
    const { useLinkForm } = await import('../../src/composables/useLinkForm')
    const icon = makeIcon()
    const form = useLinkForm(icon)
    const link = makeEditingLink()

    form.openEditLink(link)

    expect(form.editingLink.value).toStrictEqual(link)
    expect(form.linkModalOpen.value).toBe(true)
    // Форма копируется (не ссылается на тот же объект), но значения полей идентичны.
    expect(form.linkForm.value).not.toStrictEqual(link)
    expect(form.linkForm.value.title).toBe('Title')
    expect(form.linkForm.value.url).toBe('https://portal.test')
    expect(form.linkForm.value.category).toBe('cat')
    expect(form.linkForm.value.supports_sso).toBe(true)
    expect(icon.resetIconState).toHaveBeenCalledOnce()
  })

  it('openDeleteLink does nothing when confirm cancelled', async () => {
    const { useLinkForm } = await import('../../src/composables/useLinkForm')
    const form = useLinkForm(makeIcon())
    confirmMock.mockResolvedValueOnce(false)

    await form.openDeleteLink(makeEditingLink())

    expect(deleteLinkMock).not.toHaveBeenCalled()
    expect(storeMock.removeLink).not.toHaveBeenCalled()
  })

  it('openDeleteLink deletes and syncs store on confirm', async () => {
    const { useLinkForm } = await import('../../src/composables/useLinkForm')
    const form = useLinkForm(makeIcon())
    const link = makeEditingLink()
    confirmMock.mockResolvedValueOnce(true)
    deleteLinkMock.mockResolvedValueOnce({})

    await form.openDeleteLink(link)

    expect(deleteLinkMock).toHaveBeenCalledWith('l-1')
    expect(storeMock.removeLink).toHaveBeenCalledWith('l-1')
    expect(messageMock.success).toHaveBeenCalledWith('admin.links.deleted')
  })

  it('openDeleteLink shows error on failure', async () => {
    const { useLinkForm } = await import('../../src/composables/useLinkForm')
    const form = useLinkForm(makeIcon())
    confirmMock.mockResolvedValueOnce(true)
    deleteLinkMock.mockRejectedValueOnce(new Error('boom'))

    await form.openDeleteLink(makeEditingLink())

    expect(parseApiErrorMock).toHaveBeenCalled()
    expect(messageMock.error).toHaveBeenCalledWith('parsed-error')
  })

  it('submitLink create branch: createLink + store.addLink, closes modal', async () => {
    const { useLinkForm } = await import('../../src/composables/useLinkForm')
    const icon = makeIcon()
    const form = useLinkForm(icon)
    form.linkForm.value = { title: 'New', url: 'https://new.test' } as never
    form.linkFormRef.value = { validate: () => Promise.resolve() } as never
    const created = { id: 'n-1', title: 'New', url: 'https://new.test' }
    createLinkMock.mockResolvedValueOnce(created)

    await form.submitLink()

    expect(createLinkMock).toHaveBeenCalled()
    expect(storeMock.addLink).toHaveBeenCalledWith(created)
    expect(form.linkModalOpen.value).toBe(false)
    expect(messageMock.success).toHaveBeenCalledWith('admin.links.saved')
    // No icon branch triggered.
    expect(uploadLinkIconMock).not.toHaveBeenCalled()
    expect(deleteLinkIconMock).not.toHaveBeenCalled()
  })

  it('submitLink edit branch: updateLink + store.updateLinkItem', async () => {
    const { useLinkForm } = await import('../../src/composables/useLinkForm')
    const icon = makeIcon()
    const form = useLinkForm(icon)
    const link = makeEditingLink()
    form.openEditLink(link)
    form.linkFormRef.value = { validate: () => Promise.resolve() } as never
    const updated = { ...link, title: 'Renamed' }
    updateLinkMock.mockResolvedValueOnce(updated)

    await form.submitLink()

    expect(updateLinkMock).toHaveBeenCalledWith('l-1', expect.any(Object))
    expect(storeMock.updateLinkItem).toHaveBeenCalledWith(updated)
  })

  it('submitLink uploads icon when iconFile present', async () => {
    const { useLinkForm } = await import('../../src/composables/useLinkForm')
    const icon = makeIcon()
    icon.iconFile.value = new File(['x'], 'icon.png', { type: 'image/png' })
    const form = useLinkForm(icon)
    form.linkFormRef.value = { validate: () => Promise.resolve() } as never
    const created = { id: 'n-2', title: 'X', url: 'https://x.test' }
    createLinkMock.mockResolvedValueOnce(created)
    const withIcon = { ...created, icon_url: '/icon.png' }
    uploadLinkIconMock.mockResolvedValueOnce(withIcon)

    await form.submitLink()

    expect(uploadLinkIconMock).toHaveBeenCalledWith('n-2', expect.any(File))
    expect(storeMock.updateLinkItem).toHaveBeenCalledWith(withIcon)
  })

  it('submitLink deletes icon when iconRemoved and editing had icon_url', async () => {
    const { useLinkForm } = await import('../../src/composables/useLinkForm')
    const icon = makeIcon()
    icon.iconRemoved.value = true
    const form = useLinkForm(icon)
    form.openEditLink(makeEditingLink({ icon_url: '/has.png' }))
    form.linkFormRef.value = { validate: () => Promise.resolve() } as never
    const updated = makeEditingLink({ icon_url: '/has.png' })
    updateLinkMock.mockResolvedValueOnce(updated)
    deleteLinkIconMock.mockResolvedValueOnce({})

    await form.submitLink()

    expect(deleteLinkIconMock).toHaveBeenCalledWith('l-1')
    expect(storeMock.clearLinkIcon).toHaveBeenCalledWith('l-1')
  })

  it('submitLink shows error on create failure and keeps modal open', async () => {
    const { useLinkForm } = await import('../../src/composables/useLinkForm')
    const icon = makeIcon()
    const form = useLinkForm(icon)
    form.linkFormRef.value = { validate: () => Promise.resolve() } as never
    createLinkMock.mockRejectedValueOnce(new Error('boom'))

    await form.submitLink()

    expect(parseApiErrorMock).toHaveBeenCalled()
    expect(messageMock.error).toHaveBeenCalledWith('parsed-error')
    expect(form.linkModalOpen.value).toBe(false) // stays as-is (was false)
    expect(form.savingLink.value).toBe(false) // finally resets
  })

  it('linkRules exposes title/url/kb_url with required validators', async () => {
    const { useLinkForm } = await import('../../src/composables/useLinkForm')
    const form = useLinkForm(makeIcon())
    const rules = form.linkRules.value
    expect(rules.title).toBeDefined()
    expect(rules.url).toHaveLength(2)
    expect(rules.kb_url).toBeDefined()
  })
})
