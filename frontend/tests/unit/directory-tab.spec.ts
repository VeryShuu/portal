/**
 * Юнит-тесты DirectoryTab.vue: рендер карточек, debounce-поиск → query-параметр,
 * экспорт через window.location.assign, открытие drawer настроек типа.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, type Ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\', $event)"><slot name="icon" /><slot /></button>',
    props: ['type', 'quaternary', 'circle', 'title'],
    emits: ['click'],
  },
  NIcon: { template: '<span><slot /></span>' },
  NInput: {
    template: '<input class="search" :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'clearable'],
    emits: ['update:value'],
  },
  NDropdown: {
    template: '<div class="dropdown" @click="$emit(\'select\', \'pdf\')"><slot /></div>',
    props: ['trigger', 'options'],
    emits: ['select'],
  },
  NDrawer: { template: '<div class="n-drawer"><slot /></div>', props: ['show', 'width', 'placement'] },
  NDrawerContent: { template: '<div><slot /></div>', props: ['title', 'closable'] },
  useMessage: () => ({ error: vi.fn(), success: vi.fn() }),
}))

let sortableOnEnd: ((evt: { oldIndex?: number; newIndex?: number }) => void) | undefined
vi.mock('sortablejs', () => ({
  default: {
    create: (_el: unknown, opts: { onEnd?: typeof sortableOnEnd }) => {
      sortableOnEnd = opts.onEnd
      return { destroy: vi.fn() }
    },
  },
}))

vi.mock('@vicons/ionicons5', () => ({
  AddOutline: { template: '<span />' },
  DownloadOutline: { template: '<span />' },
  SearchOutline: { template: '<span />' },
  SettingsOutline: { template: '<span />' },
}))

const entriesData: Ref<{ items: unknown[] } | undefined> = ref({ items: [] })
const refetchSpy = vi.fn()
let capturedParams: { value: { q?: string; limit: number; offset: number } } | undefined

vi.mock('../../src/queries/directories', () => ({
  useDirectoryEntriesQuery: (_slug: unknown, params: unknown) => {
    capturedParams = params as typeof capturedParams
    return { data: entriesData, isLoading: ref(false), refetch: refetchSpy }
  },
  useReorderEntriesMutation: () => ({ mutateAsync: reorderSpy }),
}))

vi.mock('../../src/api/directories', () => ({
  buildEntriesExportUrl: (slug: string, fmt: string) => `EXPORT:${slug}:${fmt}`,
}))

const openSpy = vi.fn()
const reorderSpy = vi.fn().mockResolvedValue(undefined)
vi.mock('../../src/composables/useManageDrawer', () => ({
  useManageDrawer: () => ({ open: openSpy, close: vi.fn(), is: () => false }),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => ({ isAdmin: true, isEditor: false }),
}))

const directory = {
  id: 'd1',
  slug: 'fleet',
  label_ru: 'Флот',
  label_en: 'Fleet',
  icon: null,
  description: null,
  field_schema: [],
  channels: [],
  enabled: true,
  sort_order: 0,
  created_at: '',
  updated_at: '',
}

async function mountTab() {
  const { default: DirectoryTab } = await import('../../src/pages/staff/DirectoryTab.vue')
  return mount(DirectoryTab, {
    props: { directory },
    global: {
      plugins: [i18n],
      stubs: {
        EmptyState: true,
        SkeletonCard: true,
        EntryCard: { template: '<div class="entry-card-stub" />', props: ['entry'] },
        EntryEditDrawer: true,
        DirectorySettings: true,
      },
    },
  })
}

describe('DirectoryTab.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    entriesData.value = { items: [] }
    refetchSpy.mockReset()
    openSpy.mockReset()
    reorderSpy.mockClear()
    sortableOnEnd = undefined
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders one EntryCard per entry', async () => {
    entriesData.value = { items: [{ id: 'e1' }, { id: 'e2' }] }
    const wrapper = await mountTab()
    expect(wrapper.findAll('.entry-card-stub')).toHaveLength(2)
  })

  it('shows EmptyState when no entries', async () => {
    const wrapper = await mountTab()
    expect(wrapper.find('.entry-card-stub').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'EmptyState' }).exists()).toBe(true)
  })

  it('debounces search input into the query params', async () => {
    vi.useFakeTimers()
    const wrapper = await mountTab()
    await wrapper.find('input.search').setValue('Kaz')
    expect(capturedParams?.value.q).toBeUndefined()
    vi.advanceTimersByTime(300)
    await Promise.resolve()
    expect(capturedParams?.value.q).toBe('Kaz')
  })

  it('exports via window.location.assign with built url', async () => {
    const assign = vi.fn()
    Object.defineProperty(window, 'location', { configurable: true, value: { assign } })
    const wrapper = await mountTab()
    await wrapper.find('.dropdown').trigger('click')
    expect(assign).toHaveBeenCalledWith('EXPORT:fleet:pdf')
  })

  it('opens settings drawer for admin', async () => {
    const wrapper = await mountTab()
    const manageBtn = wrapper.findAll('.n-button').at(-1)!
    await manageBtn.trigger('click')
    expect(openSpy).toHaveBeenCalledWith('directory')
  })

  it('persists new sort_order on drag end', async () => {
    entriesData.value = { items: [{ id: 'e1' }, { id: 'e2' }, { id: 'e3' }] }
    await mountTab()
    await Promise.resolve()
    expect(sortableOnEnd).toBeTypeOf('function')
    sortableOnEnd!({ oldIndex: 0, newIndex: 2 })
    expect(reorderSpy).toHaveBeenCalledWith([
      { id: 'e2', sort_order: 0 },
      { id: 'e3', sort_order: 1 },
      { id: 'e1', sort_order: 2 },
    ])
  })
})
