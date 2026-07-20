import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /><slot name="icon" /></button>',
    props: ['type', 'size', 'text', 'disabled', 'loading', 'quaternary', 'circle', 'title', 'ghost', 'attrType', 'block'],
    emits: ['click'],
  },
  NDropdown: {
    template: '<div class="n-dropdown"><slot /></div>',
    props: ['options', 'trigger'],
    emits: ['select'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color', 'component'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  AddOutline: { template: '<span />' },
  SettingsOutline: { template: '<span />' },
  SyncOutline: { template: '<span />' },
  ImageOutline: { template: '<span />' },
  ShareSocialOutline: { template: '<span />' },
}))

describe('FilesSidebar.vue', () => {
  it('renders without errors', async () => {
    const FilesSidebar = (await import('../../src/components/files/FilesSidebar.vue')).default
    const wrapper = mount(FilesSidebar, {
      props: {
        tree: [],
        loading: false,
        selectedId: null,
        isAdmin: false,
        isEditor: false,
        syncing: false,
      },
      global: {
        plugins: [i18n],
        stubs: {
          SkeletonCard: { template: '<div class="skeleton-card" />' },
          FileFolderNode: { template: '<li class="folder-node" />' },
        },
      },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows empty state text when no tree items', async () => {
    const FilesSidebar = (await import('../../src/components/files/FilesSidebar.vue')).default
    const wrapper = mount(FilesSidebar, {
      props: {
        tree: [],
        loading: false,
        selectedId: null,
        isAdmin: false,
        isEditor: false,
        syncing: false,
      },
      global: {
        plugins: [i18n],
        stubs: {
          SkeletonCard: { template: '<div class="skeleton-card" />' },
          FileFolderNode: { template: '<li class="folder-node" />' },
        },
      },
    })
    expect(wrapper.find('.files-side__empty').exists()).toBe(true)
  })

  it('shows sync button for admin', async () => {
    const FilesSidebar = (await import('../../src/components/files/FilesSidebar.vue')).default
    const wrapper = mount(FilesSidebar, {
      props: {
        tree: [],
        loading: false,
        selectedId: null,
        isAdmin: true,
        isEditor: true,
        syncing: false,
      },
      global: {
        plugins: [i18n],
        stubs: {
          SkeletonCard: { template: '<div class="skeleton-card" />' },
          FileFolderNode: { template: '<li class="folder-node" />' },
        },
      },
    })
    expect(wrapper.find('.n-dropdown').exists()).toBe(true)
  })

  it('shows loading skeletons when loading=true', async () => {
    const FilesSidebar = (await import('../../src/components/files/FilesSidebar.vue')).default
    const wrapper = mount(FilesSidebar, {
      props: {
        tree: [],
        loading: true,
        selectedId: null,
        isAdmin: false,
        isEditor: false,
        syncing: false,
      },
      global: {
        plugins: [i18n],
        stubs: {
          SkeletonCard: { template: '<div class="skeleton-card" />' },
          FileFolderNode: { template: '<li class="folder-node" />' },
        },
      },
    })
    expect(wrapper.findAll('.skeleton-card').length).toBeGreaterThan(0)
  })

  it('renders folder tree when tree items present', async () => {
    const FilesSidebar = (await import('../../src/components/files/FilesSidebar.vue')).default
    const tree = [{ id: 'f1', name: 'Folder 1', children: [], path: '/folder1', nc_path: '/nc/folder1', parent_id: null }]
    const wrapper = mount(FilesSidebar, {
      props: {
        tree,
        loading: false,
        selectedId: null,
        isAdmin: false,
        isEditor: false,
        syncing: false,
      },
      global: {
        plugins: [i18n],
        stubs: {
          SkeletonCard: { template: '<div class="skeleton-card" />' },
          FileFolderNode: { template: '<li class="folder-node" />' },
        },
      },
    })
    expect(wrapper.find('.folder-tree').exists()).toBe(true)
    expect(wrapper.findAll('.folder-node').length).toBe(1)
  })
})
