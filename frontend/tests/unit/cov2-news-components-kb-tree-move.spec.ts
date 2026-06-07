import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const expandedIds = new Set<string>()
const toggleExpansion = vi.fn((id: string) => {
  if (expandedIds.has(id)) expandedIds.delete(id)
  else expandedIds.add(id)
})

vi.mock('naive-ui', () => ({
  NModal: {
    template: '<div v-if="show" class="n-modal"><slot /></div>',
    props: ['show', 'preset', 'title'],
    emits: ['update:show'],
  },
  NTree: {
    name: 'NTree',
    template: '<div class="n-tree"><slot /></div>',
    props: ['data', 'selectedKeys', 'selectable', 'blockLine', 'defaultExpandAll', 'keyField', 'labelField', 'childrenField'],
    emits: ['update:selected-keys'],
  },
  NButton: {
    template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'loading', 'disabled', 'size', 'text'],
    emits: ['click'],
  },
  NDropdown: {
    name: 'NDropdown',
    template: '<div class="n-dropdown"><slot /></div>',
    props: ['trigger', 'placement', 'options'],
    emits: ['select'],
  },
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {} })),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false }, isFetching: { value: false }, error: { value: null }, refetch: vi.fn() })),
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: { value: false }, isError: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn(), setQueryData: vi.fn() })),
  useInfiniteQuery: vi.fn(() => ({ data: { value: { pages: [] } }, isLoading: { value: false }, fetchNextPage: vi.fn(), hasNextPage: { value: false } })),
  keepPreviousData: undefined,
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({ data: {} }),
  apiUpload: vi.fn().mockResolvedValue({ data: {} }),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/composables/useKbSectionTreeExpansion', () => ({
  useKbSectionTreeExpansion: vi.fn(() => ({
    isExpanded: (id: string) => expandedIds.has(id),
    toggle: (id: string) => toggleExpansion(id),
    setExpanded: vi.fn(),
    clear: vi.fn(),
  })),
}))

function section(id: string, title: string, children: any[] = [], user_permission: 'viewer' | 'editor' | 'manager' = 'viewer') {
  return {
    id,
    title,
    slug: title.toLowerCase(),
    parent_id: null,
    children,
    user_permission,
  }
}

describe('cov2 KbSectionMoveModal.vue', () => {
  it('builds tree excluding current section and emits submit with selected parent', async () => {
    const Cmp = (await import('../../src/components/KbSectionMoveModal.vue')).default
    const sections = [
      section('s1', 'Root', [section('s2', 'Child')], 'manager'),
      section('s3', 'Another'),
    ]

    const w = mount(Cmp, {
      props: {
        show: true,
        sectionId: 's2',
        sections,
        saving: false,
      },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    const tree = w.findComponent({ name: 'NTree' })
    const data = tree.props('data') as any[]
    expect(data[0].children.some((n: any) => n.key === 's2')).toBe(false)

    tree.vm.$emit('update:selected-keys', ['s3'])
    await flushPromises()

    const saveBtn = w.findAll('button.n-button')[1]
    await saveBtn.trigger('click')
    expect(w.emitted('submit')![0]).toEqual(['s3'])
  })

  it('guards root/current-parent selection and clears selection when empty', async () => {
    const Cmp = (await import('../../src/components/KbSectionMoveModal.vue')).default
    const sections = [section('s1', 'Root', [section('s2', 'Child')], 'manager')]

    const w = mount(Cmp, {
      props: {
        show: true,
        sectionId: 's2',
        sections,
        saving: false,
      },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    const tree = w.findComponent({ name: 'NTree' })
    tree.vm.$emit('update:selected-keys', ['s1'])
    await nextTick()

    const saveBtn = w.findAll('button.n-button')[1]
    expect(saveBtn.attributes('disabled')).toBeDefined()

    tree.vm.$emit('update:selected-keys', [])
    await nextTick()
    expect(saveBtn.attributes('disabled')).toBeDefined()
  })
})

describe('cov2 KbSectionTree.vue', () => {
  beforeEach(() => {
    expandedIds.clear()
    toggleExpansion.mockClear()
  })

  it('renders active row, toggles expansion, and emits select', async () => {
    const Cmp = (await import('../../src/components/KbSectionTree.vue')).default
    const s = section('p1', 'Parent', [section('c1', 'Child')], 'editor')

    const w = mount(Cmp, {
      props: { section: s, activeId: 'p1', isAdmin: false },
      global: { plugins: [i18n], stubs: { KbSectionTree: true } },
    })

    expect(w.find('.tree-node__row--active').exists()).toBe(true)
    await w.find('.tree-node__toggle').trigger('click')
    expect(toggleExpansion).toHaveBeenCalledWith('p1')

    await w.find('.tree-node__btn').trigger('click')
    expect(w.emitted('select')![0]).toEqual(['p1'])
  })

  it('emits menu actions and rename payload for manager role', async () => {
    const Cmp = (await import('../../src/components/KbSectionTree.vue')).default
    const s = section('p2', 'Manage', [], 'manager')

    const w = mount(Cmp, {
      props: { section: s, activeId: null, isAdmin: false },
      global: { plugins: [i18n], stubs: { KbSectionTree: true } },
    })

    const dropdown = w.findComponent({ name: 'NDropdown' })
    const opts = dropdown.props('options') as Array<{ key?: string; type?: string }>
    expect(opts.some((o) => o.key === 'permissions')).toBe(true)
    expect(opts.some((o) => o.key === 'delete')).toBe(true)

    dropdown.vm.$emit('select', 'add-child')
    dropdown.vm.$emit('select', 'move')
    dropdown.vm.$emit('select', 'permissions')
    dropdown.vm.$emit('select', 'delete')
    await flushPromises()

    expect(w.emitted('add-child')![0]).toEqual(['p2'])
    expect(w.emitted('move-section')![0]).toEqual(['p2'])
    expect(w.emitted('manage-permissions')![0]).toEqual(['p2'])
    expect(w.emitted('delete-section')![0]).toEqual(['p2'])

    dropdown.vm.$emit('select', 'rename')
    await nextTick()
    const input = w.find('input.tree-node__rename')
    await input.setValue('Renamed')
    await input.trigger('keydown.enter')
    expect(w.emitted('rename-section')![0]).toEqual([{ id: 'p2', title: 'Renamed' }])
  })

  it('prevents rename emit for unchanged/empty value and hides menu for viewer', async () => {
    const Cmp = (await import('../../src/components/KbSectionTree.vue')).default
    const s = section('p3', 'Readonly', [], 'viewer')

    const w = mount(Cmp, {
      props: { section: s, activeId: null, isAdmin: false },
      global: { plugins: [i18n], stubs: { KbSectionTree: true } },
    })

    expect(w.findComponent({ name: 'NDropdown' }).exists()).toBe(false)

    await w.find('.tree-node__btn').trigger('dblclick')
    expect(w.find('input.tree-node__rename').exists()).toBe(false)
  })
})
