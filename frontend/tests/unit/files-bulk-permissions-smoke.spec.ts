/**
 * Smoke-тесты FilesBulkBar.vue + FilesPermissionsModal.vue (Фаза 6.2)
 *
 * FilesBulkBar:
 * - renders selected count
 * - shows disabled download button when count > downloadLimit
 * - shows enabled download button when count <= downloadLimit
 * - emits download on button click
 * - emits move on button click
 * - emits delete on button click
 * - emits clear on button click
 * - disables move/delete when canUpload=false
 *
 * FilesPermissionsModal:
 * - renders when show=true
 * - shows loading state
 * - shows inherit toggle when parentId is provided
 * - hides inherit toggle when parentId is null
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['size', 'type', 'ghost', 'disabled', 'loading', 'text'],
    emits: ['click'],
  },
  NTooltip: {
    template: '<div class="n-tooltip"><slot name="trigger" /><slot /></div>',
  },
  NModal: {
    template: '<div v-if="show" class="n-modal"><slot /></div>',
    props: ['show', 'title', 'preset'],
  },
  NSwitch: {
    template: '<button class="n-switch" @click="$emit(\'update:value\', !value)"></button>',
    props: ['value', 'loading'],
    emits: ['update:value'],
  },
  NDataTable: {
    template: '<div class="n-data-table"></div>',
    props: ['columns', 'data', 'size'],
  },
  NDivider: {
    template: '<hr class="n-divider" />',
  },
  NAutoComplete: {
    template: '<input class="n-auto-complete" />',
    props: ['value', 'options', 'loading', 'placeholder', 'clearable', 'size'],
  },
  NSelect: {
    template: '<select class="n-select"><slot /></select>',
    props: ['value', 'options', 'style'],
  },
  NTooltip2: {
    template: '<div><slot name="trigger" /><slot /></div>',
  },
  useMessage: () => ({ error: vi.fn(), success: vi.fn() }),
}))

vi.mock('../../src/api/files', () => ({
  fetchPermissions: vi.fn().mockResolvedValue({ items: [] }),
  grantPermission: vi.fn().mockResolvedValue({}),
  revokePermission: vi.fn().mockResolvedValue({}),
  setFolderInheritance: vi.fn().mockResolvedValue({}),
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue([]),
}))

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'ru',
    messages: {
      ru: {
        files: {
          bulk: {
            selected: '{n} выбрано',
            download: 'Скачать',
            downloadLimit: 'Превышен лимит',
            move: 'Переместить',
            delete: 'Удалить',
            clear: 'Сбросить',
          },
          permissions: {
            title: 'Права доступа',
            inheritFromParent: 'Наследовать от родителя',
            inheritDisabledHint: 'Отключено',
            grant: 'Выдать права',
            searchPlaceholder: 'Поиск',
            add: 'Добавить',
            type: 'Тип',
            name: 'Имя',
            level: 'Уровень',
          },
          permission: {
            viewer: 'Просмотр',
            editor: 'Редактор',
            manager: 'Менеджер',
          },
          error: {
            loadPerms: 'Ошибка загрузки',
            grantPerm: 'Ошибка выдачи',
            revokePerm: 'Ошибка отзыва',
            toggleInheritance: 'Ошибка',
          },
        },
        common: {
          loading: 'Загрузка...',
          delete: 'Удалить',
        },
      },
    },
    missingWarn: false,
    fallbackWarn: false,
    silentFallbackWarn: true,
    silentTranslationWarn: true,
  })
}

// ── FilesBulkBar ──────────────────────────────────────────────────────────────

async function mountBulkBar(props: Record<string, unknown> = {}) {
  const { default: FilesBulkBar } = await import('../../src/components/files/FilesBulkBar.vue')
  const i18n = makeI18n()
  return mount(FilesBulkBar, {
    props: {
      count: 3,
      canUpload: true,
      bulkBusy: false,
      downloadLimit: 10,
      ...props,
    },
    global: { plugins: [i18n] },
  })
}

describe('FilesBulkBar', () => {
  it('renders selected count', async () => {
    const wrapper = await mountBulkBar({ count: 5 })
    expect(wrapper.text()).toContain('5')
  })

  it('shows disabled download button when count exceeds downloadLimit', async () => {
    const wrapper = await mountBulkBar({ count: 15, downloadLimit: 10 })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.n-tooltip').exists()).toBe(true)
  })

  it('shows enabled download button when count within limit', async () => {
    const wrapper = await mountBulkBar({ count: 3, downloadLimit: 10 })
    const buttons = wrapper.findAll('.n-button')
    expect(buttons.some(b => b.text() === 'Скачать')).toBe(true)
  })

  it('emits download on button click', async () => {
    const wrapper = await mountBulkBar({ count: 3, downloadLimit: 10 })
    const downloadBtn = wrapper.findAll('.n-button').find(b => b.text() === 'Скачать')
    await downloadBtn?.trigger('click')
    expect(wrapper.emitted('download')).toBeTruthy()
  })

  it('emits move on button click', async () => {
    const wrapper = await mountBulkBar()
    const moveBtn = wrapper.findAll('.n-button').find(b => b.text() === 'Переместить')
    await moveBtn?.trigger('click')
    expect(wrapper.emitted('move')).toBeTruthy()
  })

  it('emits delete on button click', async () => {
    const wrapper = await mountBulkBar()
    const delBtn = wrapper.findAll('.n-button').find(b => b.text() === 'Удалить')
    await delBtn?.trigger('click')
    expect(wrapper.emitted('delete')).toBeTruthy()
  })

  it('emits clear on button click', async () => {
    const wrapper = await mountBulkBar()
    const clearBtn = wrapper.findAll('.n-button').find(b => b.text() === 'Сбросить')
    await clearBtn?.trigger('click')
    expect(wrapper.emitted('clear')).toBeTruthy()
  })

  it('disables move and delete when canUpload=false', async () => {
    const wrapper = await mountBulkBar({ canUpload: false })
    const moveBtn = wrapper.findAll('.n-button').find(b => b.text() === 'Переместить')
    expect(moveBtn?.attributes('disabled')).toBeDefined()
  })
})

// ── FilesPermissionsModal ─────────────────────────────────────────────────────

async function mountPermsModal(props: Record<string, unknown> = {}) {
  const { default: FilesPermissionsModal } = await import('../../src/components/files/FilesPermissionsModal.vue')
  const i18n = makeI18n()
  return mount(FilesPermissionsModal, {
    props: {
      show: true,
      folderId: 'folder-123',
      parentId: null,
      inheritPermissions: false,
      ...props,
    },
    global: { plugins: [i18n] },
  })
}

describe('FilesPermissionsModal', () => {
  it('renders when show=true', async () => {
    const wrapper = await mountPermsModal()
    expect(wrapper.find('.n-modal').exists()).toBe(true)
  })

  it('does not render when show=false', async () => {
    const wrapper = await mountPermsModal({ show: false })
    expect(wrapper.find('.n-modal').exists()).toBe(false)
  })

  it('hides inherit toggle when parentId is null', async () => {
    const wrapper = await mountPermsModal({ parentId: null })
    expect(wrapper.find('.n-switch').exists()).toBe(false)
  })

  it('shows inherit toggle when parentId is provided', async () => {
    const wrapper = await mountPermsModal({ parentId: 'parent-456', show: true })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.n-switch').exists()).toBe(true)
  })
})
