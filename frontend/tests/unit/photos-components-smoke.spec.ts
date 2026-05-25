/**
 * Smoke-тесты Photos компонентов (Фаза 6.4)
 *
 * PhotosGrid:
 * - renders without errors with no photos
 * - renders loading skeletons when loading=true
 * - renders photo items
 * - emits photo-click on cell click
 * - shows load-more button when totalPhotos > photos.length
 * - shows multiselect toolbar when selectMode=true
 * - shows empty state when no photos and not loading
 * - emits load-more on button click
 *
 * LightboxModal:
 * - renders nothing when modelValue=null
 * - renders when modelValue is provided
 * - shows close button
 * - shows nav buttons
 * - emits update:modelValue null on close click
 *
 * PhotoTrashView:
 * - renders without errors
 * - shows empty state when no photos
 * - shows empty trash button for admin when photos present
 * - hides empty trash button when not admin
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['size', 'type', 'ghost', 'disabled', 'loading'],
    emits: ['click'],
  },
  NDropdown: {
    template: '<div class="n-dropdown"><slot /></div>',
    props: ['options', 'trigger'],
    emits: ['select'],
  },
  NModal: {
    template: '<div v-if="show" class="n-modal"><slot /></div>',
    props: ['show', 'preset', 'title'],
    emits: ['update:show'],
  },
  NForm: {
    template: '<form class="n-form"><slot /></form>',
  },
  NFormItem: {
    template: '<div class="n-form-item"><slot /></div>',
    props: ['label'],
  },
  NInput: {
    template: '<input class="n-input" :value="value" />',
    props: ['value', 'readonly'],
  },
  NSelect: {
    template: '<select class="n-select"><slot /></select>',
    props: ['value', 'options', 'multiple', 'filterable', 'placeholder', 'size'],
  },
  NTag: {
    template: '<span class="n-tag"><slot /></span>',
    props: ['size'],
  },
  useMessage: () => ({ error: vi.fn(), success: vi.fn() }),
}))

vi.mock('@/api/photos', () => ({
  thumbUrl: (id: string, size: number) => `/thumbs/${id}/${size}`,
  thumbAvifUrl: (id: string, size: number) => `/thumbs/${id}/${size}/avif`,
  originalUrl: (id: string) => `/photos/${id}/original`,
  createShareLink: vi.fn().mockResolvedValue({ token: 'tok' }),
  createFolderShareLink: vi.fn().mockResolvedValue({ token: 'ftok' }),
  fetchPhotoTags: vi.fn().mockResolvedValue([]),
  setPhotoTags: vi.fn().mockResolvedValue([]),
  fetchDeletedPhotos: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchDeletedFolders: vi.fn().mockResolvedValue([]),
  restorePhoto: vi.fn().mockResolvedValue({}),
  restoreFolder: vi.fn().mockResolvedValue({}),
  purgePhoto: vi.fn().mockResolvedValue({}),
  emptyTrash: vi.fn().mockResolvedValue({ purged: 0 }),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: () => ({
    ensureQueryData: vi.fn().mockResolvedValue([]),
    setQueryData: vi.fn(),
  }),
  useQuery: vi.fn(),
  useMutation: vi.fn(),
}))

vi.mock('@/composables/useInterval', () => ({
  useInterval: () => ({
    isActive: { value: false },
    start: vi.fn(),
    stop: vi.fn(),
    restart: vi.fn(),
  }),
}))

vi.mock('@/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: vi.fn().mockResolvedValue(true) }),
}))

vi.mock('../../src/components/EmptyState.vue', () => ({
  default: {
    template: '<div class="empty-state">{{ title }}</div>',
    props: ['variant', 'title', 'description'],
  },
}))

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'ru',
    messages: {
      ru: {
        photos: {
          empty: 'Нет фото',
          upload: { dropHere: 'Перетащите сюда' },
          select: { count: '{n} выбрано', delete: 'Удалить', move: 'Переместить', cancel: 'Отмена' },
          lightbox: {
            zoomOut: 'Уменьшить',
            zoomIn: 'Увеличить',
            rotate: 'Повернуть',
            rotateRight: 'Повернуть вправо',
            reset: 'Сброс',
            slideshow: 'Слайдшоу',
            slideshowStop: 'Стоп',
            slideshow5s: '5с',
            slideshow10s: '10с',
            slideshow30s: '30с',
            download: 'Скачать',
            copyLink: 'Скопировать',
            createShareLink: 'Поделиться',
            generate: 'Создать',
            expiresIn: 'Срок',
            expires1d: '1 день',
            expires7d: '7 дней',
            expires30d: '30 дней',
            expires90d: '90 дней',
            expiresNever: 'Никогда',
            shareLinkCreated: 'Создана',
            copied: 'Скопировано',
          },
          myShares: { shareFolder: 'Папка' },
          tags: { addTags: 'Добавить теги', saveTags: 'Сохранить', saved: 'Сохранено' },
          trash: {
            button: 'Корзина',
            emptyAll: 'Очистить',
            emptyAllConfirm: 'Удалить все?',
            emptyAllDone: 'Удалено {n}',
            back: 'Назад',
            restore: 'Восстановить',
            restoreDone: 'Восстановлено',
            purgeTitle: 'Удалить',
            purgeConfirm: 'Удалить навсегда?',
            purgeDone: 'Удалено',
            emptyTitle: 'Корзина пуста',
          },
          folders: { title: 'Папки' },
        },
        common: {
          loadMore: 'Ещё',
          close: 'Закрыть',
          prev: 'Назад',
          next: 'Вперёд',
          cancel: 'Отмена',
          delete: 'Удалить',
          copy: 'Копировать',
        },
        errors: { generic: 'Ошибка' },
      },
    },
    missingWarn: false,
    fallbackWarn: false,
    silentFallbackWarn: true,
    silentTranslationWarn: true,
  })
}

function makePhoto(id: string = 'photo-1') {
  return {
    id,
    original_name: `photo-${id}.jpg`,
    folder_id: 'folder-1',
    filename: `${id}.jpg`,
    taken_at: null,
    width: 1920,
    height: 1080,
    file_size: 102400,
    created_at: '2024-01-01T00:00:00Z',
    is_deleted: false,
    thumb_small: null,
    thumb_medium: null,
  }
}

// ── PhotosGrid ────────────────────────────────────────────────────────────────

describe('PhotosGrid', () => {
  async function mount_(props: Record<string, unknown> = {}) {
    const { default: PhotosGrid } = await import('../../src/components/photos/PhotosGrid.vue')
    return mount(PhotosGrid, {
      props: {
        photos: [],
        totalPhotos: 0,
        loading: false,
        selectMode: false,
        selectedPhotoIds: new Set<string>(),
        canUpload: false,
        canDelete: () => false,
        isDraggingOver: false,
        ...props,
      },
      global: {
        plugins: [makeI18n()],
        stubs: { EmptyState: { template: '<div class="empty-state">{{ title }}</div>', props: ['variant', 'title', 'description'] } },
      },
    })
  }

  it('renders without errors with empty photos', async () => {
    const w = await mount_()
    expect(w.exists()).toBe(true)
  })

  it('shows empty state when no photos and not loading', async () => {
    const w = await mount_({ photos: [], loading: false })
    expect(w.find('.empty-state').exists()).toBe(true)
  })

  it('renders loading skeletons when loading=true', async () => {
    const w = await mount_({ loading: true })
    expect(w.find('.photo-skeleton').exists()).toBe(true)
  })

  it('renders photo items', async () => {
    const photos = [makePhoto('p-1'), makePhoto('p-2')]
    const w = await mount_({ photos, totalPhotos: 2 })
    expect(w.findAll('.photo-cell').length).toBe(2)
  })

  it('emits photo-click on cell click', async () => {
    const photo = makePhoto('click-me')
    const w = await mount_({ photos: [photo], totalPhotos: 1 })
    await w.find('.photo-cell').trigger('click')
    expect(w.emitted('photo-click')).toBeTruthy()
  })

  it('shows load-more button when totalPhotos > photos.length', async () => {
    const w = await mount_({ photos: [makePhoto()], totalPhotos: 10 })
    expect(w.find('.photo-loadmore').exists()).toBe(true)
  })

  it('hides load-more when all photos loaded', async () => {
    const w = await mount_({ photos: [makePhoto()], totalPhotos: 1 })
    expect(w.find('.photo-loadmore').exists()).toBe(false)
  })

  it('shows multiselect toolbar when selectMode=true', async () => {
    const w = await mount_({ selectMode: true, selectedPhotoIds: new Set(['p-1']) })
    expect(w.find('.multiselect-toolbar').exists()).toBe(true)
  })
})

// ── LightboxModal ─────────────────────────────────────────────────────────────

describe('LightboxModal', () => {
  async function mount_(props: Record<string, unknown> = {}) {
    const { default: LightboxModal } = await import('../../src/components/photos/LightboxModal.vue')
    return mount(LightboxModal, {
      props: {
        modelValue: null,
        photos: [],
        selectedFolder: null,
        selectedFolderId: null,
        canUpload: false,
        canManage: false,
        tags: [],
        photoTagsMap: {},
        ...props,
      },
      global: { plugins: [makeI18n()] },
    })
  }

  it('renders nothing when modelValue=null', async () => {
    const w = await mount_({ modelValue: null })
    expect(w.find('.lightbox').exists()).toBe(false)
  })

  it('renders when modelValue is a valid index', async () => {
    const photos = [makePhoto('lb-1')]
    const w = await mount_({ modelValue: 0, photos })
    expect(w.find('.lightbox').exists()).toBe(true)
  })

  it('shows close button', async () => {
    const photos = [makePhoto('lb-2')]
    const w = await mount_({ modelValue: 0, photos })
    expect(w.find('.lightbox__close').exists()).toBe(true)
  })

  it('shows prev and next nav buttons', async () => {
    const photos = [makePhoto('lb-3'), makePhoto('lb-4')]
    const w = await mount_({ modelValue: 0, photos })
    expect(w.find('.lightbox__nav--prev').exists()).toBe(true)
    expect(w.find('.lightbox__nav--next').exists()).toBe(true)
  })

  it('emits update:modelValue null on close button click', async () => {
    const photos = [makePhoto('lb-5')]
    const w = await mount_({ modelValue: 0, photos })
    await w.find('.lightbox__close').trigger('click')
    const emitted = w.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual([null])
  })

  it('shows toolbar', async () => {
    const photos = [makePhoto('lb-6')]
    const w = await mount_({ modelValue: 0, photos })
    expect(w.find('.lightbox__toolbar').exists()).toBe(true)
  })
})

// ── PhotoTrashView ────────────────────────────────────────────────────────────

describe('PhotoTrashView', () => {
  async function mount_(props: Record<string, unknown> = {}) {
    const { default: PhotoTrashView } = await import('../../src/components/photos/PhotoTrashView.vue')
    return mount(PhotoTrashView, {
      props: { isAdmin: false, ...props },
      global: { plugins: [makeI18n()] },
    })
  }

  it('renders without errors', async () => {
    const w = await mount_()
    expect(w.exists()).toBe(true)
  })

  it('shows empty state text when no photos loaded', async () => {
    const w = await mount_()
    await flushPromises()
    expect(w.find('.photos-empty-state').exists()).toBe(true)
  })

  it('hides empty trash button when not admin', async () => {
    const w = await mount_({ isAdmin: false })
    await w.vm.$nextTick()
    const buttons = w.findAll('.n-button')
    const emptyBtn = buttons.find(b => b.text() === 'Очистить')
    expect(emptyBtn).toBeUndefined()
  })

  it('shows back button when not embedded', async () => {
    const w = await mount_({ isAdmin: false, embedded: false })
    await w.vm.$nextTick()
    const buttons = w.findAll('.n-button')
    expect(buttons.some(b => b.text() === 'Назад')).toBe(true)
  })

  it('hides back button when embedded=true', async () => {
    const w = await mount_({ embedded: true })
    await w.vm.$nextTick()
    const buttons = w.findAll('.n-button')
    expect(buttons.some(b => b.text() === 'Назад')).toBe(false)
  })
})
