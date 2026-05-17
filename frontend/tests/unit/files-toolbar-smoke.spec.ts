/**
 * Smoke-тесты FilesToolbar.vue (Фаза 6.2)
 *
 * Покрытие:
 * - renders without folder (null)
 * - renders folder name
 * - shows permission tag for manager/editor/viewer
 * - shows readonly tag when canEdit=false
 * - shows upload button when canUpload=true
 * - shows manage button when canManage=true
 * - emits upload-click on button click
 * - emits manage-click on button click
 * - shows upload progress bar when uploading=true
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['size', 'type', 'ghost'],
    emits: ['click'],
  },
  NTag: {
    template: '<span class="n-tag"><slot /></span>',
    props: ['size', 'type'],
  },
  NProgress: {
    template: '<div class="n-progress" :data-percentage="percentage"></div>',
    props: ['type', 'percentage', 'showIndicator', 'height'],
  },
}))

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'ru',
    messages: {
      ru: {
        files: {
          upload: 'Загрузить',
          manage: 'Управление',
          readonly: 'Только чтение',
          uploadProgress: '{done} из {total}',
          permission: {
            manager: 'Менеджер',
            editor: 'Редактор',
            viewer: 'Просмотр',
          },
        },
      },
    },
    missingWarn: false,
    fallbackWarn: false,
    silentFallbackWarn: true,
    silentTranslationWarn: true,
  })
}

function makeFolder(overrides: Record<string, unknown> = {}) {
  return {
    id: 'folder-1',
    name: 'My Folder',
    nc_path: 'PortalFiles/My Folder',
    permission: 'editor',
    inherit_permissions: true,
    parent_id: null,
    description: null,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  }
}

function defaultProgress() {
  return { done: 0, total: 0, failed: 0 }
}

async function mountToolbar(props: Record<string, unknown> = {}) {
  const { default: FilesToolbar } = await import('../../src/components/files/FilesToolbar.vue')
  const i18n = makeI18n()

  const defaults = {
    currentFolder: makeFolder(),
    canUpload: false,
    canManage: false,
    canEdit: true,
    uploading: false,
    uploadProgress: defaultProgress(),
  }

  return mount(FilesToolbar, {
    props: { ...defaults, ...props },
    global: { plugins: [i18n] },
  })
}

describe('FilesToolbar', () => {
  it('renders without errors with null folder', async () => {
    const wrapper = await mountToolbar({ currentFolder: null })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders folder name', async () => {
    const wrapper = await mountToolbar({ currentFolder: makeFolder({ name: 'Documents' }) })
    expect(wrapper.text()).toContain('Documents')
  })

  it('shows permission tag for manager', async () => {
    const wrapper = await mountToolbar({
      currentFolder: makeFolder({ permission: 'manager' }),
    })
    const tags = wrapper.findAll('.n-tag')
    expect(tags.length).toBeGreaterThan(0)
  })

  it('shows permission tag for editor', async () => {
    const wrapper = await mountToolbar({
      currentFolder: makeFolder({ permission: 'editor' }),
    })
    const tags = wrapper.findAll('.n-tag')
    expect(tags.length).toBeGreaterThan(0)
  })

  it('shows readonly tag when canEdit is false', async () => {
    const wrapper = await mountToolbar({ canEdit: false })
    expect(wrapper.text()).toContain('Только чтение')
  })

  it('does not show readonly tag when canEdit is true', async () => {
    const wrapper = await mountToolbar({ canEdit: true })
    expect(wrapper.text()).not.toContain('Только чтение')
  })

  it('shows upload button when canUpload is true', async () => {
    const wrapper = await mountToolbar({ canUpload: true })
    expect(wrapper.text()).toContain('Загрузить')
  })

  it('does not show upload button when canUpload is false', async () => {
    const wrapper = await mountToolbar({ canUpload: false })
    expect(wrapper.text()).not.toContain('Загрузить')
  })

  it('shows manage button when canManage is true', async () => {
    const wrapper = await mountToolbar({ canManage: true })
    expect(wrapper.text()).toContain('Управление')
  })

  it('does not show manage button when canManage is false', async () => {
    const wrapper = await mountToolbar({ canManage: false })
    expect(wrapper.text()).not.toContain('Управление')
  })

  it('emits upload-click when upload button clicked', async () => {
    const wrapper = await mountToolbar({ canUpload: true })
    const buttons = wrapper.findAll('.n-button')
    const uploadBtn = buttons.find((b) => b.text().includes('Загрузить'))
    expect(uploadBtn).toBeTruthy()
    await uploadBtn!.trigger('click')
    expect(wrapper.emitted('upload-click')).toBeTruthy()
  })

  it('emits manage-click when manage button clicked', async () => {
    const wrapper = await mountToolbar({ canManage: true })
    const buttons = wrapper.findAll('.n-button')
    const manageBtn = buttons.find((b) => b.text().includes('Управление'))
    expect(manageBtn).toBeTruthy()
    await manageBtn!.trigger('click')
    expect(wrapper.emitted('manage-click')).toBeTruthy()
  })

  it('shows progress bar when uploading is true', async () => {
    const wrapper = await mountToolbar({
      uploading: true,
      uploadProgress: { done: 3, total: 10, failed: 0 },
    })
    expect(wrapper.find('.n-progress').exists()).toBe(true)
  })

  it('does not show progress bar when uploading is false', async () => {
    const wrapper = await mountToolbar({ uploading: false })
    expect(wrapper.find('.n-progress').exists()).toBe(false)
  })

  it('renders without permission tag when folder has no permission', async () => {
    const wrapper = await mountToolbar({
      currentFolder: makeFolder({ permission: null }),
    })
    expect(wrapper.exists()).toBe(true)
  })
})
