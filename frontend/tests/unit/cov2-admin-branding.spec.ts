import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import { ref } from 'vue'

const {
  useQueryMock,
  useInfiniteQueryMock,
  queryClientMock,
  messageMock,
  brandingStoreState,
  brandingStore,
} = vi.hoisted(() => {
  const settings = {
    portal_name: 'Portal',
    portal_tagline: 'Tagline',
    accent_color: '#3366aa',
    logo_hidden: false,
    banner_enabled: false,
    banner_text: '',
    banner_type: 'info',
    banner_expires_at: '',
  }
  const state = {
    assets: {
      logo: '',
      favicon: '',
      'login-bg': '',
    } as Record<string, string>,
  }
  return {
    useQueryMock: vi.fn(),
    useInfiniteQueryMock: vi.fn(),
    queryClientMock: {
      invalidateQueries: vi.fn().mockResolvedValue(undefined),
      removeQueries: vi.fn(),
      setQueryData: vi.fn(),
    },
    messageMock: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
    brandingStoreState: state,
    brandingStore: {
      settings,
      load: vi.fn().mockResolvedValue(undefined),
      save: vi.fn().mockResolvedValue(undefined),
      uploadAsset: vi.fn().mockResolvedValue(undefined),
      resetAsset: vi.fn().mockResolvedValue(undefined),
      assetUrl: vi.fn((kind: string) => state.assets[kind] ?? ''),
    },
  }
})

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: { template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /><slot name="icon" /></button>', props: ['type', 'size', 'disabled', 'loading', 'ghost', 'quaternary', 'tertiary', 'circle', 'title'], emits: ['click'] },
  NButtonGroup: { template: '<div><slot /></div>' },
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NEmpty: { template: '<div class="n-empty"><slot /></div>', props: ['description'] },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'title', 'showIcon', 'closable'] },
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'size'], emits: ['update:value'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color', 'component'] },
  NCard: { template: '<div class="n-card"><slot /></div>', props: ['bordered', 'size', 'title'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type', 'maxlength', 'size', 'clearable'],
    emits: ['update:value'],
  },
  NSelect: {
    template: '<select :value="value" @change="$emit(\'update:value\', $event.target.value)"><option v-for="o in options || []" :key="o.value" :value="o.value">{{ o.label }}</option></select>',
    props: ['value', 'options', 'placeholder', 'multiple', 'clearable'],
    emits: ['update:value'],
  },
  NPagination: { template: '<div class="n-pagination" />', props: ['page', 'pageCount', 'pageSize'], emits: ['update:page'] },
  NRadioGroup: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NRadioButton: { template: '<label><slot /></label>', props: ['value', 'label'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /></div>', props: ['show', 'title', 'preset'], emits: ['update:show'] },
  NDrawer: { template: '<div class="n-drawer" v-if="show"><slot /></div>', props: ['show', 'width', 'placement'], emits: ['update:show'] },
  NDrawerContent: { template: '<div><slot /></div>', props: ['title', 'closable'] },
  NForm: { template: '<form><slot /></form>', props: ['model', 'rules'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path'] },
  NCheckbox: { template: '<input type="checkbox" :checked="checked" @change="$emit(\'update:checked\', !checked)" />', props: ['checked'], emits: ['update:checked'] },
  NSwitch: { template: '<input type="checkbox" :checked="value" @change="$emit(\'update:value\', !value)" />', props: ['value'], emits: ['update:value'] },
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
  NInputNumber: { template: '<input type="number" :value="value" @input="$emit(\'update:value\', Number($event.target.value))" />', props: ['value', 'min', 'max'], emits: ['update:value'] },
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
  useMessage: () => messageMock,
  useDialog: () => ({ warning: vi.fn(), error: vi.fn(), success: vi.fn() }),
  useLoadingBar: () => ({ start: vi.fn(), finish: vi.fn(), error: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/admin', name: 'admin' })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: useQueryMock,
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: { value: false }, isError: { value: false } })),
  useQueryClient: vi.fn(() => queryClientMock),
  useInfiniteQuery: useInfiniteQueryMock,
  keepPreviousData: undefined,
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({ data: {} }),
  apiUpload: vi.fn().mockResolvedValue({ data: {} }),
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/stores/branding', () => ({
  useBrandingStore: () => brandingStore,
}))

vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))
vi.mock('@vicons/fluent', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
  },
}

describe('cov2 admin tabs: branding', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    brandingStoreState.assets.logo = ''
    brandingStoreState.assets.favicon = ''
    brandingStoreState.assets['login-bg'] = ''
    useInfiniteQueryMock.mockReturnValue({ data: ref({ pages: [] }), isLoading: ref(false), fetchNextPage: vi.fn(), hasNextPage: ref(false) })
    useQueryMock.mockReturnValue({ data: ref(undefined), isLoading: ref(false), isFetching: ref(false), error: ref(null), isError: ref(false), refetch: vi.fn() })
  })

  it('BrandingTab mounts with placeholder branch when no assets', async () => {
    const Component = (await import('../../src/pages/admin/tabs/BrandingTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('admin.branding.logoDefault')
    expect(wrapper.text()).not.toContain('admin.branding.resetLogo')
  })

  it('BrandingTab renders asset branches and reset buttons', async () => {
    brandingStoreState.assets.logo = '/logo.png'
    brandingStoreState.assets.favicon = '/favicon.ico'
    brandingStoreState.assets['login-bg'] = '/bg.png'

    const Component = (await import('../../src/pages/admin/tabs/BrandingTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.findAll('img').length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('admin.branding.resetLogo')
    expect(wrapper.text()).toContain('admin.branding.resetFavicon')
    expect(wrapper.text()).toContain('admin.branding.resetLoginBg')
  })

  it('BrandingTab save button calls store save', async () => {
    const Component = (await import('../../src/pages/admin/tabs/BrandingTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    const saveButtons = wrapper.findAll('button').filter((b) => b.text().includes('common.save'))
    expect(saveButtons.length).toBeGreaterThan(0)

    await saveButtons[0].trigger('click')
    await flushPromises()

    expect(brandingStore.save).toHaveBeenCalled()
    expect(messageMock.success).toHaveBeenCalled()
  })
})
