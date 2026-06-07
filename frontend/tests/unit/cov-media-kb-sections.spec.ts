import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import type { KbSection } from '../../src/api/kb'

const mockCreateMutateAsync = vi.fn()
const mockUpdateMutateAsync = vi.fn()
const mockDeleteMutateAsync = vi.fn()
const mockConfirm = vi.fn()
const mockSetQueryData = vi.fn()

const mockMessageSuccess = vi.fn()
const mockMessageError = vi.fn()

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('naive-ui', () => ({
  useMessage: () => ({
    success: mockMessageSuccess,
    error: mockMessageError,
    warning: vi.fn(),
  }),
}))

const sectionsData = ref<{ items: KbSection[] } | undefined>(undefined)
const sectionsLoading = ref(false)

vi.mock('../../src/queries/kb', () => ({
  useKbSectionsQuery: () => ({ data: sectionsData, isLoading: sectionsLoading }),
  useCreateKbSectionMutation: () => ({ mutateAsync: mockCreateMutateAsync }),
  useUpdateKbSectionMutation: () => ({ mutateAsync: mockUpdateMutateAsync }),
  useDeleteKbSectionMutation: () => ({ mutateAsync: mockDeleteMutateAsync }),
}))

vi.mock('../../src/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: (...args: unknown[]) => mockConfirm(...args) }),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: () => ({ setQueryData: (...args: unknown[]) => mockSetQueryData(...args) }),
}))

vi.mock('../../src/api/index', () => ({ api: vi.fn() }))

import { useKbSections, findSectionRecursive } from '../../src/composables/useKbSections'

type KbApi = ReturnType<typeof useKbSections>

async function setupHost(): Promise<{ api: KbApi; router: Router }> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()

  let api: KbApi | null = null

  const Host = defineComponent({
    setup() {
      api = useKbSections()
      return () => h('div')
    },
  })

  mount(Host, { global: { plugins: [router] } })
  return { api: api as unknown as KbApi, router }
}

function makeSection(id: string, children: KbSection[] = [], inherit_permissions = true): KbSection {
  return {
    id,
    title: `s-${id}`,
    description: null,
    parent_id: null,
    sort_order: 0,
    user_permission: null,
    children,
    inherit_permissions,
    permissions: [],
    created_at: '',
    updated_at: '',
  }
}

describe('cov-media useKbSections', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sectionsData.value = { items: [makeSection('a', [makeSection('a1', [], false)]), makeSection('b')] }
    sectionsLoading.value = false
  })

  it('findSectionRecursive returns nested section or null', () => {
    const tree = [makeSection('root', [makeSection('child')])]
    expect(findSectionRecursive(tree, 'child')?.id).toBe('child')
    expect(findSectionRecursive(tree, 'missing')).toBeNull()
  })

  it('initializes selectedSection from localStorage and persists updates', async () => {
    localStorage.setItem('kb.section-tree.selected', 'a1')
    const { api } = await setupHost()

    expect(api.selectedSection.value).toBe('a1')

    api.selectedSection.value = 'b'
    await Promise.resolve()
    expect(localStorage.getItem('kb.section-tree.selected')).toBe('b')

    api.selectedSection.value = null
    await Promise.resolve()
    expect(localStorage.getItem('kb.section-tree.selected')).toBeNull()
  })

  it('handles localStorage get/set failures silently', async () => {
    const getItemSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })

    const { api } = await setupHost()
    expect(api.selectedSection.value).toBeNull()

    api.selectedSection.value = 'x'
    await Promise.resolve()
    expect(setItemSpy).toHaveBeenCalled()

    getItemSpy.mockRestore()
    setItemSpy.mockRestore()
  })

  it('sectionPermsInherit branches by selected section existence', async () => {
    const { api } = await setupHost()

    api.sectionPermsId.value = null
    expect(api.sectionPermsInherit.value).toBe(true)

    api.sectionPermsId.value = 'a1'
    expect(api.sectionPermsInherit.value).toBe(false)

    api.sectionPermsId.value = 'missing'
    expect(api.sectionPermsInherit.value).toBe(true)
  })

  it('onSectionInheritChanged returns early without sectionPermsId', async () => {
    const { api } = await setupHost()

    api.sectionPermsId.value = null
    api.onSectionInheritChanged(false)

    expect(mockSetQueryData).not.toHaveBeenCalled()
  })

  it('onSectionInheritChanged updates cached tree when old data exists', async () => {
    const { api } = await setupHost()
    api.sectionPermsId.value = 'a1'

    let patched: { items: KbSection[] } | undefined
    mockSetQueryData.mockImplementation((_key, updater: (old: { items: KbSection[] } | undefined) => { items: KbSection[] } | undefined) => {
      patched = updater({ items: [makeSection('a', [makeSection('a1', [], true)])] })
      return patched
    })

    api.onSectionInheritChanged(false)

    expect(mockSetQueryData).toHaveBeenCalledTimes(1)
    expect(findSectionRecursive(patched?.items ?? [], 'a1')?.inherit_permissions).toBe(false)
  })

  it('open helpers set modal state and ids', async () => {
    const { api } = await setupHost()

    api.openMoveSection('sec-9')
    expect(api.moveSectionId.value).toBe('sec-9')
    expect(api.showMoveModal.value).toBe(true)

    api.openSectionPermissions('sec-2')
    expect(api.sectionPermsId.value).toBe('sec-2')
    expect(api.showSectionPermsModal.value).toBe(true)

    api.openCreateSection('parent-1')
    expect(api.showSectionModal.value).toBe(true)
    expect(api.sectionForm.value).toEqual({ title: '', description: '', parent_id: 'parent-1' })
  })

  it('submitMoveSection handles guard, success and error paths', async () => {
    const { api } = await setupHost()

    await api.submitMoveSection('p-1')
    expect(mockUpdateMutateAsync).not.toHaveBeenCalled()

    api.moveSectionId.value = 's-1'
    mockUpdateMutateAsync.mockResolvedValueOnce({})
    await api.submitMoveSection('p-2')

    expect(mockUpdateMutateAsync).toHaveBeenCalledWith({ id: 's-1', dto: { parent_id: 'p-2' } })
    expect(api.showMoveModal.value).toBe(false)
    expect(api.moveSectionId.value).toBeNull()
    expect(mockMessageSuccess).toHaveBeenCalledWith('kb.section.moveSuccess')
    expect(api.moveSaving.value).toBe(false)

    api.moveSectionId.value = 's-2'
    mockUpdateMutateAsync.mockRejectedValueOnce(new Error('x'))
    await api.submitMoveSection(null)

    expect(mockMessageError).toHaveBeenCalledWith('kb.section.moveError')
    expect(api.moveSaving.value).toBe(false)
  })

  it('submitCreateSection handles empty-title guard, success and error', async () => {
    const { api } = await setupHost()

    api.sectionForm.value = { title: '   ', description: '', parent_id: null }
    await api.submitCreateSection()
    expect(mockCreateMutateAsync).not.toHaveBeenCalled()

    api.sectionForm.value = { title: '  My Section  ', description: '', parent_id: 'root' }
    mockCreateMutateAsync.mockResolvedValueOnce({})
    await api.submitCreateSection()

    expect(mockCreateMutateAsync).toHaveBeenCalledWith({
      title: 'My Section',
      description: null,
      parent_id: 'root',
      sort_order: 0,
    })
    expect(api.showSectionModal.value).toBe(false)
    expect(mockMessageSuccess).toHaveBeenCalledWith('kb.section.createSuccess')
    expect(api.sectionSaving.value).toBe(false)

    api.sectionForm.value = { title: 'Err', description: 'd', parent_id: null }
    mockCreateMutateAsync.mockRejectedValueOnce(new Error('err'))
    await api.submitCreateSection()

    expect(mockMessageError).toHaveBeenCalledWith('kb.section.createError')
    expect(api.sectionSaving.value).toBe(false)
  })

  it('renameSection shows success and error messages', async () => {
    const { api } = await setupHost()

    mockUpdateMutateAsync.mockResolvedValueOnce({})
    await api.renameSection({ id: 's-1', title: 'New' })
    expect(mockMessageSuccess).toHaveBeenCalledWith('kb.section.renameSuccess')

    mockUpdateMutateAsync.mockRejectedValueOnce(new Error('e'))
    await api.renameSection({ id: 's-2', title: 'Fail' })
    expect(mockMessageError).toHaveBeenCalledWith('kb.section.renameError')
  })

  it('confirmDeleteSection handles cancel, success, selected reset, and error', async () => {
    const { api } = await setupHost()

    api.selectedSection.value = 's-1'
    mockConfirm.mockResolvedValueOnce(false)
    await api.confirmDeleteSection('s-1')
    expect(mockDeleteMutateAsync).not.toHaveBeenCalled()

    mockConfirm.mockResolvedValueOnce(true)
    mockDeleteMutateAsync.mockResolvedValueOnce({})
    await api.confirmDeleteSection('s-1')
    expect(api.selectedSection.value).toBeNull()
    expect(mockMessageSuccess).toHaveBeenCalledWith('kb.section.deleteSuccess')

    mockConfirm.mockResolvedValueOnce(true)
    mockDeleteMutateAsync.mockRejectedValueOnce(new Error('e'))
    await api.confirmDeleteSection('s-2')
    expect(mockMessageError).toHaveBeenCalledWith('kb.section.deleteError')
  })
})
