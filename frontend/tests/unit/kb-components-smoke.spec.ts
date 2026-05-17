/**
 * Smoke-тесты KB компонентов (Фаза 6.3)
 *
 * KbSectionTree:
 * - renders section title
 * - emits select on button click
 * - shows active state when activeId matches
 * - shows delete button when isAdmin=true
 * - hides delete button when isAdmin=false
 * - shows expand toggle when section has children
 *
 * KbArticleCommentsTab:
 * - renders without errors
 * - shows textarea input
 * - shows submit button
 *
 * KbArticleVersionsTab:
 * - renders without errors
 * - shows empty state when no versions
 * - renders version items when versions exist
 *
 * KbPermissionsModal:
 * - renders when modelValue=true
 * - does not render when modelValue=false
 * - shows inherit toggle for article type
 * - hides inherit toggle for section type
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" :loading="loading" @click="$emit(\'click\')"><slot /></button>',
    props: ['size', 'type', 'text', 'loading', 'disabled'],
    emits: ['click'],
  },
  NInput: {
    template: '<textarea class="n-input" :value="value" @input="$emit(\'update:value\', $event.target.value)"></textarea>',
    props: ['value', 'type', 'placeholder', 'autosize'],
    emits: ['update:value'],
  },
  NModal: {
    template: '<div v-if="show" class="n-modal"><slot /></div>',
    props: ['show', 'modelValue', 'preset', 'title'],
    emits: ['update:show'],
  },
  NSwitch: {
    template: '<button class="n-switch"></button>',
    props: ['value', 'modelValue'],
    emits: ['update:value', 'update:modelValue'],
  },
  NSelect: {
    template: '<select class="n-select"><slot /></select>',
    props: ['value', 'options', 'size'],
  },
  NAutoComplete: {
    template: '<input class="n-auto-complete" />',
    props: ['value', 'options', 'loading', 'placeholder', 'clearable', 'size'],
  },
  NTag: {
    template: '<span class="n-tag"><slot /></span>',
    props: ['size'],
  },
  useMessage: () => ({ error: vi.fn(), success: vi.fn() }),
}))

vi.mock('../../src/api/kb', () => ({
  fetchComments: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createComment: vi.fn().mockResolvedValue({}),
  deleteComment: vi.fn().mockResolvedValue({}),
  fetchVersions: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}))

vi.mock('../../src/queries/kb', () => ({
  useRestoreKbVersionMutation: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
  }),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => ({
    isAdmin: false,
    user: { id: 'user-1', role: 'reader' },
  }),
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({ items: [] }),
}))

vi.mock('../../src/utils/formatDate', () => ({
  formatDate: (d: string) => d,
}))

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'ru',
    messages: {
      ru: {
        kb: {
          add_subsection: 'Добавить подраздел',
          'section.delete': 'Удалить раздел',
          'permissions.title': 'Права',
          deletedComment: 'Удалено',
          commentPlaceholder: 'Введите комментарий',
          submitComment: 'Отправить',
          diff: { compare: 'Сравнить' },
          restoreVersion: 'Восстановить',
          noVersions: 'Нет версий',
          versionRestored: 'Версия восстановлена',
          permissions: {
            title: 'Права',
            inheritFromSection: 'Наследовать',
            empty: 'Нет прав',
            searchPlaceholder: 'Поиск',
            add: 'Добавить',
            permViewer: 'Просмотр',
            permEditor: 'Редактор',
            permManager: 'Менеджер',
            addedSuccess: 'Выдано',
            revokedSuccess: 'Отозвано',
          },
        },
        common: {
          error: 'Ошибка',
          loadError: 'Ошибка загрузки',
          saveError: 'Ошибка сохранения',
          delete: 'Удалить',
          cancel: 'Отмена',
        },
      },
    },
    missingWarn: false,
    fallbackWarn: false,
    silentFallbackWarn: true,
    silentTranslationWarn: true,
  })
}

function makeSection(overrides: Record<string, unknown> = {}) {
  return {
    id: 'sec-1',
    title: 'Test Section',
    slug: 'test-section',
    parent_id: null,
    children: [],
    ...overrides,
  }
}

// ── KbSectionTree ─────────────────────────────────────────────────────────────

describe('KbSectionTree', () => {
  async function mount_(props: Record<string, unknown> = {}) {
    const { default: KbSectionTree } = await import('../../src/components/KbSectionTree.vue')
    return mount(KbSectionTree, {
      props: {
        section: makeSection(),
        activeId: null,
        isAdmin: false,
        ...props,
      },
      global: { plugins: [makeI18n()] },
    })
  }

  it('renders section title', async () => {
    const w = await mount_({ section: makeSection({ title: 'My Section' }) })
    expect(w.text()).toContain('My Section')
  })

  it('emits select on button click', async () => {
    const w = await mount_({ section: makeSection({ id: 'sec-42' }) })
    await w.find('.tree-node__btn').trigger('click')
    expect(w.emitted('select')).toBeTruthy()
    expect(w.emitted('select')![0]).toEqual(['sec-42'])
  })

  it('shows active state when activeId matches', async () => {
    const w = await mount_({ section: makeSection({ id: 'sec-1' }), activeId: 'sec-1' })
    expect(w.find('.tree-node__btn--active').exists()).toBe(true)
  })

  it('does not show active state when activeId differs', async () => {
    const w = await mount_({ activeId: 'other-id' })
    expect(w.find('.tree-node__btn--active').exists()).toBe(false)
  })

  it('shows delete button when isAdmin=true', async () => {
    const w = await mount_({ isAdmin: true })
    expect(w.find('.tree-node__action-btn--delete').exists()).toBe(true)
  })

  it('hides delete button when isAdmin=false', async () => {
    const w = await mount_({ isAdmin: false })
    expect(w.find('.tree-node__action-btn--delete').exists()).toBe(false)
  })

  it('shows expand toggle when section has children', async () => {
    const section = makeSection({ children: [makeSection({ id: 'child-1', title: 'Child' })] })
    const w = await mount_({ section })
    expect(w.find('.tree-node__toggle').exists()).toBe(true)
  })

  it('hides expand toggle when section has no children', async () => {
    const w = await mount_({ section: makeSection({ children: [] }) })
    expect(w.find('.tree-node__toggle').exists()).toBe(false)
  })
})

// ── KbArticleCommentsTab ──────────────────────────────────────────────────────

describe('KbArticleCommentsTab', () => {
  async function mount_(props: Record<string, unknown> = {}) {
    const { default: KbArticleCommentsTab } = await import('../../src/components/KbArticleCommentsTab.vue')
    return mount(KbArticleCommentsTab, {
      props: { articleId: 'art-1', ...props },
      global: { plugins: [makeI18n()] },
    })
  }

  it('renders without errors', async () => {
    const w = await mount_()
    expect(w.exists()).toBe(true)
  })

  it('shows textarea input', async () => {
    const w = await mount_()
    expect(w.find('.n-input').exists()).toBe(true)
  })

  it('shows submit button', async () => {
    const w = await mount_()
    const buttons = w.findAll('.n-button')
    expect(buttons.some(b => b.text().includes('Отправить'))).toBe(true)
  })
})

// ── KbArticleVersionsTab ──────────────────────────────────────────────────────

describe('KbArticleVersionsTab', () => {
  async function mount_(props: Record<string, unknown> = {}) {
    const { default: KbArticleVersionsTab } = await import('../../src/components/KbArticleVersionsTab.vue')

    vi.mock('../../src/components/EmptyState.vue', () => ({
      default: { template: '<div class="empty-state"><slot /></div>', props: ['variant', 'title', 'description'] },
    }))

    return mount(KbArticleVersionsTab, {
      props: { articleId: 'art-1', currentVersion: 3, canRestore: true, ...props },
      global: {
        plugins: [makeI18n()],
        stubs: {
          EmptyState: { template: '<div class="empty-state">{{ title }}</div>', props: ['variant', 'title', 'description'] },
        },
      },
    })
  }

  it('renders without errors', async () => {
    const w = await mount_()
    expect(w.exists()).toBe(true)
  })

  it('shows empty state when no versions loaded', async () => {
    const w = await mount_()
    await w.vm.$nextTick()
    expect(w.find('.empty-state').exists()).toBe(true)
  })
})

// ── KbPermissionsModal ────────────────────────────────────────────────────────

describe('KbPermissionsModal', () => {
  async function mount_(props: Record<string, unknown> = {}) {
    const { default: KbPermissionsModal } = await import('../../src/components/KbPermissionsModal.vue')
    return mount(KbPermissionsModal, {
      props: {
        modelValue: true,
        resourceType: 'section',
        resourceId: 'sec-1',
        ...props,
      },
      global: { plugins: [makeI18n()] },
    })
  }

  it('renders when modelValue=true', async () => {
    const w = await mount_()
    expect(w.find('.n-modal').exists()).toBe(true)
  })

  it('does not render when modelValue=false', async () => {
    const w = await mount_({ modelValue: false })
    expect(w.find('.n-modal').exists()).toBe(false)
  })

  it('hides inherit toggle for section type', async () => {
    const w = await mount_({ resourceType: 'section', modelValue: true })
    await w.vm.$nextTick()
    expect(w.find('.n-switch').exists()).toBe(false)
  })

  it('shows inherit toggle for article type', async () => {
    const w = await mount_({ resourceType: 'article', modelValue: true, inheritPermissions: true })
    await w.vm.$nextTick()
    expect(w.find('.n-switch').exists()).toBe(true)
  })

  it('shows empty permissions message', async () => {
    const w = await mount_({ modelValue: true })
    await w.vm.$nextTick()
    expect(w.text()).toContain('Нет прав')
  })
})
