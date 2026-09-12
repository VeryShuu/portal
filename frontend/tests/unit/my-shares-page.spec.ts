import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'loading', 'block', 'text', 'ghost', 'quaternary', 'secondary', 'tertiary', 'circle', 'title'],
    emits: ['click'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('@/api/photos', () => ({
  thumbUrl: vi.fn((id: string, size: number) => `/photos/thumb/${id}/${size}`),
}))

vi.mock('../../src/queries/photos', async () => {
  const { ref } = await import('vue')
  return {
    useMySharesQuery: vi.fn(() => ({
      data: ref({ photo_tokens: [{ id: 't1', photo_id: 'p1', url: 'http://portal/pub/photo/tok1' }], folder_tokens: [{ id: 't2', folder_id: 'f1', url: 'http://portal/pub/folder/tok2' }] }),
      isLoading: ref(false),
    })),
    useRevokePhotoShareMutation: vi.fn(() => ({ mutateAsync: photoRevoke, isPending: ref(false) })),
    useRevokeFolderShareMutation: vi.fn(() => ({ mutateAsync: folderRevoke, isPending: ref(false) })),
  }
})

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'error'),
}))

const globalPlugins = {
  plugins: [i18n],
}

// Ссылки на моки revoke-мутаций: фабрика vi.mock hoisted, поэтому vi.hoisted.
const { photoRevoke, folderRevoke } = vi.hoisted(() => ({
  photoRevoke: vi.fn().mockResolvedValue(undefined),
  folderRevoke: vi.fn().mockResolvedValue(undefined),
}))

describe('MySharesPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    photoRevoke.mockClear()
    folderRevoke.mockClear()
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      writable: true,
      configurable: true,
    })
  })

  it('renders without errors', async () => {
    const MySharesPage = (await import('../../src/pages/photos/MySharesPage.vue')).default
    const wrapper = mount(MySharesPage, { global: globalPlugins })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders the shares page element', async () => {
    const MySharesPage = (await import('../../src/pages/photos/MySharesPage.vue')).default
    const wrapper = mount(MySharesPage, { global: globalPlugins })
    expect(wrapper.find('.my-shares-page').exists()).toBe(true)
  })

  it('renders one row per share with its URL (photo + folder)', async () => {
    const MySharesPage = (await import('../../src/pages/photos/MySharesPage.vue')).default
    const wrapper = mount(MySharesPage, { global: globalPlugins })

    const rows = wrapper.findAll('.share-row')
    expect(rows.length).toBe(2)
    expect(rows[0].text()).toContain('http://portal/pub/photo/tok1')
    expect(rows[1].text()).toContain('http://portal/pub/folder/tok2')
  })

  it('revoke button on photo share calls photo mutation with token id', async () => {
    const MySharesPage = (await import('../../src/pages/photos/MySharesPage.vue')).default
    const wrapper = mount(MySharesPage, { global: globalPlugins })

    // i18n messages пустые → текст кнопки = ключ ('photos.myShares.revoke')
    const revokeBtn = wrapper.findAll('button').find(b => b.text().includes('revoke'))
    expect(revokeBtn).toBeTruthy()
    await revokeBtn!.trigger('click')

    expect(photoRevoke).toHaveBeenCalledTimes(1)
    expect(photoRevoke).toHaveBeenCalledWith('t1')
    expect(folderRevoke).not.toHaveBeenCalled()
  })

  it('revoke button on folder share calls folder mutation with token id', async () => {
    const MySharesPage = (await import('../../src/pages/photos/MySharesPage.vue')).default
    const wrapper = mount(MySharesPage, { global: globalPlugins })

    const revokeBtns = wrapper.findAll('button').filter(b => b.text().includes('revoke'))
    expect(revokeBtns.length).toBe(2)
    await revokeBtns[1].trigger('click')

    expect(folderRevoke).toHaveBeenCalledTimes(1)
    expect(folderRevoke).toHaveBeenCalledWith('t2')
    expect(photoRevoke).not.toHaveBeenCalled()
  })

  it('copy button writes the share URL to clipboard', async () => {
    const MySharesPage = (await import('../../src/pages/photos/MySharesPage.vue')).default
    const wrapper = mount(MySharesPage, { global: globalPlugins })

    const copyBtn = wrapper.findAll('button').find(b => b.text().includes('copyUrl'))
    expect(copyBtn).toBeTruthy()
    await copyBtn!.trigger('click')

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('http://portal/pub/photo/tok1')
  })

  it('B1: sanitizes non-http(s) share URLs (no javascript:/data: hrefs)', async () => {
    const { ref } = await import('vue')
    const photosQueries = await import('../../src/queries/photos')
    vi.mocked(photosQueries.useMySharesQuery).mockReturnValueOnce({
      data: ref({
        photo_tokens: [{ id: 't1', photo_id: 'p1', url: 'javascript:alert(1)' }],
        folder_tokens: [{ id: 't2', folder_id: 'f1', url: 'data:text/html,<script>alert(1)</script>' }],
      }),
      isLoading: ref(false),
    } as unknown as ReturnType<typeof photosQueries.useMySharesQuery>)

    const MySharesPage = (await import('../../src/pages/photos/MySharesPage.vue')).default
    const wrapper = mount(MySharesPage, { global: globalPlugins })

    const anchors = wrapper.findAll('a')
    for (const a of anchors) {
      const href = a.attributes('href') ?? ''
      expect(href.startsWith('javascript:')).toBe(false)
      expect(href.startsWith('data:')).toBe(false)
    }
  })
})
