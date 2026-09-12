import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const ofetchMock = vi.fn()
const resetViewMock = vi.fn()
const zoomInMock = vi.fn()
const zoomOutMock = vi.fn()
const rotateLeftMock = vi.fn()
const rotateRightMock = vi.fn()
const wheelMock = vi.fn()
const loadBrandingMock = vi.fn().mockResolvedValue(undefined)

vi.mock('naive-ui', () => ({
  NButton: { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'disabled', 'loading', 'ghost', 'quaternary', 'tertiary', 'circle', 'title'], emits: ['click'] },
  NButtonGroup: { template: '<div><slot /></div>' },
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NEmpty: { template: '<div class="n-empty"><slot /></div>', props: ['description'] },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'title', 'showIcon', 'closable'] },
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'size'], emits: ['update:value'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color', 'component'] },
  NCard: { template: '<div class="n-card"><slot /></div>', props: ['bordered', 'size', 'title'] },
  NInput: { template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />', props: ['value', 'placeholder', 'type', 'maxlength', 'size', 'clearable'], emits: ['update:value'] },
  NSelect: { template: '<select />', props: ['value', 'options', 'placeholder', 'multiple', 'clearable'], emits: ['update:value'] },
  NPagination: { template: '<div class="n-pagination" />', props: ['page', 'pageCount', 'pageSize'], emits: ['update:page'] },
  NRadioGroup: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NRadioButton: { template: '<label><slot /></label>', props: ['value', 'label'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset'], emits: ['update:show'] },
  NDrawer: { template: '<div class="n-drawer" v-if="show"><slot /></div>', props: ['show', 'width', 'placement'], emits: ['update:show'] },
  NDrawerContent: { template: '<div><slot /></div>', props: ['title', 'closable'] },
  NForm: { template: '<form><slot /></form>', props: ['model', 'rules'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path'] },
  NCheckbox: { template: '<input type="checkbox" />', props: ['checked'], emits: ['update:checked'] },
  NSwitch: { template: '<input type="checkbox" />', props: ['value'], emits: ['update:value'] },
  NDataTable: { template: '<div class="n-data-table" />', props: ['data', 'columns', 'pagination', 'loading'] },
  NSpace: { template: '<div><slot /></div>', props: ['justify', 'align', 'size', 'vertical'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'closable', 'bordered'] },
  NTooltip: { template: '<div><slot /><slot name="trigger" /></div>' },
  NPopconfirm: { template: '<div><slot /><slot name="trigger" /></div>' },
  NDivider: { template: '<hr />' },
  NText: { template: '<span><slot /></span>', props: ['depth', 'type'] },
  NDynamicTags: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NUpload: { template: '<div><slot /></div>', props: ['multiple', 'showFileList', 'fileList', 'customRequest'] },
  NColorPicker: { template: '<input type="color" />', props: ['value'], emits: ['update:value'] },
  NInputNumber: { template: '<input type="number" />', props: ['value', 'min', 'max'], emits: ['update:value'] },
  NScrollbar: { template: '<div><slot /></div>' },
  NCollapse: { template: '<div><slot /></div>' },
  NCollapseItem: { template: '<div><slot /></div>', props: ['title', 'name'] },
  NCode: { template: '<pre><slot /></pre>', props: ['code', 'language'] },
  NDatePicker: { template: '<input type="date" />', props: ['value', 'type', 'placeholder'], emits: ['update:value'] },
  NSkeleton: { template: '<div class="n-skeleton" />', props: ['text', 'repeat'] },
  NTimePicker: { template: '<input type="time" />', props: ['value'], emits: ['update:value'] },
  NList: { template: '<ul><slot /></ul>' },
  NListItem: { template: '<li><slot /></li>' },
  NThing: { template: '<div><slot /></div>', props: ['title', 'description'] },
  NAvatar: { template: '<div class="n-avatar" />', props: ['src', 'size', 'round'] },
  NBadge: { template: '<div><slot /></div>', props: ['value', 'max'] },
  NDescriptions: { template: '<div><slot /></div>', props: ['column', 'bordered'] },
  NDescriptionsItem: { template: '<div><slot /></div>', props: ['label'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
  useDialog: () => ({ warning: vi.fn(), error: vi.fn(), success: vi.fn() }),
  useLoadingBar: () => ({ start: vi.fn(), finish: vi.fn(), error: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => ({ params: { token: 'pub-token' }, query: {}, path: '/photos/public', name: 'public-folder' })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false }, isFetching: { value: false }, error: { value: null }, refetch: vi.fn() })),
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: { value: false }, isError: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn(), setQueryData: vi.fn() })),
  useInfiniteQuery: vi.fn(() => ({ data: { value: { pages: [] } }, isLoading: { value: false }, fetchNextPage: vi.fn(), hasNextPage: { value: false } })),
  keepPreviousData: undefined,
}))

vi.mock('@/api', () => ({ api: vi.fn().mockResolvedValue({ data: {} }), apiUpload: vi.fn().mockResolvedValue({ data: {} }), BASE_URL: '/api/v1' }))
vi.mock('ofetch', () => ({ ofetch: (...args: unknown[]) => ofetchMock(...args) }))
vi.mock('@/api/photos', () => ({
  publicFolderInfoUrl: (token: string) => `info:${token}`,
  publicFolderPhotosUrl: (token: string, page: number, perPage: number) => `photos:${token}:${page}:${perPage}`,
  publicFolderThumbUrl: (token: string, id: string, size: number) => `thumb:${token}:${id}:${size}`,
  publicFolderAvifUrl: (token: string, id: string, size: number) => `avif:${token}:${id}:${size}`,
}))
vi.mock('@/stores/branding', () => ({
  useBrandingStore: () => ({ settings: { portal_name: 'PortalX' }, load: loadBrandingMock }),
}))
vi.mock('@/composables/useLightboxView', () => ({
  useLightboxView: () => ({
    zoom: { value: 1 },
    imgStyle: { value: { transform: 'scale(1)' } },
    resetView: resetViewMock,
    zoomIn: zoomInMock,
    zoomOut: zoomOutMock,
    rotateLeft: rotateLeftMock,
    rotateRight: rotateRightMock,
    onLightboxWheel: wheelMock,
  }),
}))
vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))
vi.mock('@vicons/fluent', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

import PublicFolderPage from '@/pages/photos/PublicFolderPage.vue'

const PhotosGridBaseStub = {
  template: '<div class="photos-grid-stub"><button class="emit-photo-click" @click="$emit(\'photo-click\', { id: \'p1\' }, 0)">open</button><slot /><slot name="empty" :photos="photos" /></div>',
  props: ['photos', 'loading'],
  emits: ['photo-click'],
}

const LightboxBaseStub = {
  template: '<div class="lightbox-base-stub" :data-model="modelValue"><button class="emit-close" @click="$emit(\'close\')">c</button><button class="emit-prev" @click="$emit(\'prev\')">p</button><button class="emit-next" @click="$emit(\'next\')">n</button><button class="emit-wheel" @click="$emit(\'wheel\', { deltaY: 1 })">w</button><button class="emit-update" @click="$emit(\'update:model-value\', null)">u</button><slot /><slot name="toolbar" /><slot name="info" /></div>',
  props: ['modelValue', 'total', 'ariaLabel'],
  emits: ['update:model-value', 'close', 'prev', 'next', 'wheel'],
}

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
    PhotosGridBase: PhotosGridBaseStub,
    PhotoThumb: { template: '<div class="photo-thumb-stub" />' },
    LightboxBase: LightboxBaseStub,
  },
}

function setupSuccessFetch(total = 1) {
  ofetchMock.mockImplementation((url?: string) => {
    const u = String(url ?? '')
    if (u.startsWith('info:')) return Promise.resolve({ folder_name: 'Public', photos_count: total })
    if (u.startsWith('photos:')) {
      const page = Number(u.split(':')[2])
      return Promise.resolve({ items: [{ id: `p${page}`, original_name: `p${page}.jpg`, width: 100, height: 100, processed: true }], total })
    }
    return Promise.reject(new Error('bad url'))
  })
}

describe('cov2 PublicFolderPage', () => {
  beforeEach(() => {
    ofetchMock.mockReset()
    resetViewMock.mockReset()
    zoomInMock.mockReset()
    zoomOutMock.mockReset()
    rotateLeftMock.mockReset()
    rotateRightMock.mockReset()
    wheelMock.mockReset()
    loadBrandingMock.mockClear()
  })

  it('renders success state and loads initial info/photos', async () => {
    setupSuccessFetch(3)
    const wrapper = mount(PublicFolderPage, { global: globalPlugins })

    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.pub-folder__main').exists()).toBe(true)
    expect(wrapper.find('.pub-folder__loadmore').exists()).toBe(true)
    expect(ofetchMock).toHaveBeenCalledWith('info:pub-token')
    expect(ofetchMock).toHaveBeenCalledWith('photos:pub-token:1:50')
  })

  it('opens lightbox and handles toolbar interactions through emitted events', async () => {
    setupSuccessFetch(1)
    const wrapper = mount(PublicFolderPage, { global: globalPlugins })

    await flushPromises()
    await wrapper.find('.emit-photo-click').trigger('click')
    await wrapper.find('.emit-prev').trigger('click')
    await wrapper.find('.emit-next').trigger('click')
    await wrapper.find('.emit-wheel').trigger('click')
    await wrapper.find('.emit-close').trigger('click')

    expect(resetViewMock).toHaveBeenCalled()
    expect(wheelMock).toHaveBeenCalled()
  })

  it('loads more photos and retries same page after failure', async () => {
    let failedPage2 = false
    ofetchMock.mockImplementation((url?: string) => {
      const u = String(url ?? '')
      if (u.startsWith('info:')) return Promise.resolve({ folder_name: 'Public', photos_count: 99 })
      if (u === 'photos:pub-token:1:50') return Promise.resolve({ items: [{ id: 'p1', original_name: 'p1.jpg', processed: true }], total: 99 })
      if (u === 'photos:pub-token:2:50' && !failedPage2) {
        failedPage2 = true
        return Promise.reject(new Error('network'))
      }
      if (u === 'photos:pub-token:2:50') return Promise.resolve({ items: [{ id: 'p2', original_name: 'p2.jpg', processed: true }], total: 99 })
      return Promise.resolve({ items: [], total: 99 })
    })

    const wrapper = mount(PublicFolderPage, { global: globalPlugins })
    await flushPromises()

    const loadBtn = wrapper.find('.pub-folder__loadmore')
    await loadBtn.trigger('click')
    await flushPromises()
    await loadBtn.trigger('click')
    await flushPromises()

    const pages = ofetchMock.mock.calls
      .map((c) => String(c[0]))
      .filter((u) => u.startsWith('photos:'))
      .map((u) => Number(u.split(':')[2]))

    expect(pages).toEqual([1, 2, 2])
  })

  it('renders gone/not_found/generic error branches', async () => {
    ofetchMock.mockRejectedValueOnce({ status: 410 })
    const gone = mount(PublicFolderPage, { global: globalPlugins })
    await flushPromises()
    expect(gone.text()).toContain('photos.public.folder.expired')

    ofetchMock.mockReset()
    ofetchMock.mockRejectedValueOnce({ response: { status: 404 } })
    const notFound = mount(PublicFolderPage, { global: globalPlugins })
    await flushPromises()
    expect(notFound.text()).toContain('photos.public.folder.notFound')

    ofetchMock.mockReset()
    ofetchMock.mockRejectedValueOnce(new Error('x'))
    const generic = mount(PublicFolderPage, { global: globalPlugins })
    await flushPromises()
    expect(generic.text()).toContain('errors.generic')
  })
})
