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
  apiMock,
  apiUploadMock,
  syncUsersFromKeycloakMock,
} = vi.hoisted(() => ({
  useQueryMock: vi.fn(),
  useInfiniteQueryMock: vi.fn(),
  queryClientMock: {
    invalidateQueries: vi.fn().mockResolvedValue(undefined),
    removeQueries: vi.fn(),
    setQueryData: vi.fn(),
    getQueryData: vi.fn(),
  },
  messageMock: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  apiMock: vi.fn(),
  apiUploadMock: vi.fn(),
  syncUsersFromKeycloakMock: vi.fn().mockResolvedValue(undefined),
}))

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: { template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /><slot name="icon" /></button>', props: ['type', 'size', 'disabled', 'loading', 'ghost', 'quaternary', 'tertiary', 'circle', 'title'], emits: ['click'] },
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NEmpty: { template: '<div class="n-empty"><slot /></div>', props: ['description'] },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'title', 'showIcon', 'closable'] },
  NTabs: { template: '<div class="n-tabs"><slot /></div>', props: ['value', 'type', 'animated', 'size'], emits: ['update:value'] },
  NTabPane: { template: '<div class="n-tab-pane"><slot /></div>', props: ['name', 'tab'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size', 'color', 'component'] },
  NCard: { template: '<div class="n-card"><slot /></div>', props: ['bordered', 'size', 'title'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type', 'maxlength', 'size', 'clearable', 'status'],
    emits: ['update:value'],
  },
  NSelect: { template: '<select />', props: ['value', 'options', 'placeholder', 'multiple', 'clearable'], emits: ['update:value'] },
  NRadioGroup: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NRadioButton: { template: '<label><slot /></label>', props: ['value', 'label'] },
  NModal: { template: '<div class="n-modal" v-if="show"><slot /><slot name="footer" /></div>', props: ['show', 'title', 'preset'], emits: ['update:show'] },
  NDrawer: { template: '<div class="n-drawer" v-if="show"><slot /></div>', props: ['show', 'width', 'placement'], emits: ['update:show'] },
  NDrawerContent: { template: '<div><slot /></div>', props: ['title', 'closable'] },
  NForm: { template: '<form><slot /></form>', props: ['model', 'rules', 'labelPlacement'] },
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
  NUpload: { template: '<div><slot /></div>', props: ['multiple', 'showFileList', 'fileList', 'customRequest'], emits: ['change'] },
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
  api: apiMock,
  apiUpload: apiUploadMock,
  BASE_URL: '/api/v1',
}))

vi.mock('../../src/api/users', () => ({
  syncUsersFromKeycloak: syncUsersFromKeycloakMock,
}))

vi.mock('@vicons/ionicons5', () => ({
  SyncOutline: { template: '<span />' },
}))
vi.mock('@vicons/fluent', () => ({}))

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
  },
}

function qResult(data: unknown, options?: { isLoading?: boolean; isError?: boolean }) {
  return {
    data: ref(data),
    isLoading: ref(options?.isLoading ?? false),
    isFetching: ref(false),
    isError: ref(options?.isError ?? false),
    error: ref(null),
    refetch: vi.fn(),
  }
}

describe('cov2 admin tabs: keycloak + system', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    useInfiniteQueryMock.mockReturnValue({ data: ref({ pages: [] }), isLoading: ref(false), fetchNextPage: vi.fn(), hasNextPage: ref(false) })
    queryClientMock.getQueryData.mockReturnValue(null)
  })

  it('KeycloakTab mounts in loading state', async () => {
    useQueryMock
      .mockReturnValueOnce(qResult(undefined, { isLoading: true }))
      .mockReturnValueOnce(qResult(null, { isLoading: true }))

    const Component = (await import('../../src/pages/admin/tabs/KeycloakTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.kc-test-result').exists()).toBe(false)
  })

  it('KeycloakTab renders loaded branches and runs oidc/sync tests', async () => {
    useQueryMock
      .mockReturnValueOnce(qResult({
        keycloak_url: 'https://kc.local',
        keycloak_realm: 'realm',
        oidc_client_id: 'cid',
        oidc_client_secret_set: true,
        sync_client_id: 'sync-id',
        sync_client_secret_set: true,
      }))
      .mockReturnValueOnce(qResult({
        last_run_at: '2026-01-01T00:00:00.000Z',
        last_count: 7,
        last_status: 'ok',
      }))

    apiMock.mockImplementation(async (url: string) => {
      if (url.includes('/test/oidc')) return { discovery_ok: true, token_ok: true, issuer: 'issuer-x' }
      if (url.includes('/test/sync')) return { token_ok: false, users_ok: false, token_error: 'bad token' }
      return {}
    })

    const Component = (await import('../../src/pages/admin/tabs/KeycloakTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.text()).toContain('7')

    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThan(3)

    await buttons[1].trigger('click')
    await flushPromises()
    expect(wrapper.find('.kc-test-result').exists()).toBe(true)

    await buttons[3].trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.kc-test-result').length).toBeGreaterThanOrEqual(1)
    expect(apiMock).toHaveBeenCalled()
  })

  it('KeycloakTab save handles API error branch', async () => {
    useQueryMock
      .mockReturnValueOnce(qResult({
        keycloak_url: 'https://kc.local',
        keycloak_realm: 'realm',
        oidc_client_id: 'cid',
        oidc_client_secret_set: false,
        sync_client_id: '',
        sync_client_secret_set: false,
      }))
      .mockReturnValueOnce(qResult(null))
    apiMock.mockRejectedValueOnce(new Error('save failed'))

    const Component = (await import('../../src/pages/admin/tabs/KeycloakTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()

    expect(messageMock.error).toHaveBeenCalled()
  })

  it('SystemTab mounts with empty data and loading', async () => {
    useQueryMock
      .mockReturnValueOnce(qResult(undefined, { isLoading: true }))
      .mockReturnValueOnce(qResult(null, { isLoading: true }))

    const Component = (await import('../../src/pages/admin/tabs/SystemTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('admin.system.tlsCertMissing')
  })

  it('SystemTab renders tls existing branches and calls nginx reload', async () => {
    useQueryMock
      .mockReturnValueOnce(qResult({
        portal_base_url: 'https://portal.local',
        timezone: 'Europe/Moscow',
        allowed_cidr: '',
        max_upload_size_mb: 100,
        news_attachment_max_size_mb: 50,
        kb_media_max_size_mb: 20,
        kb_attachment_max_size_mb: 40,
        kb_import_max_size_mb: 25,
        phone_extract_regex: '(\\d+)',
      }))
      .mockReturnValueOnce(qResult({
        cert_exists: true,
        key_exists: true,
        cert_expires_at: '2030-01-01',
        cert_subject: 'CN=portal.local',
      }))

    apiMock.mockResolvedValue({ ok: true })

    const Component = (await import('../../src/pages/admin/tabs/SystemTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    expect(wrapper.text()).toContain('admin.system.tlsDeleteCert')
    expect(wrapper.text()).toContain('admin.system.tlsDeleteKey')

    const buttons = wrapper.findAll('button')
    await buttons[1].trigger('click')
    await flushPromises()

    expect(apiMock).toHaveBeenCalled()
  })

  it('SystemTab save handles API error branch', async () => {
    useQueryMock
      .mockReturnValueOnce(qResult({
        portal_base_url: 'https://portal.local',
        timezone: 'Europe/Moscow',
        allowed_cidr: '',
        max_upload_size_mb: 100,
        news_attachment_max_size_mb: 50,
        kb_media_max_size_mb: 20,
        kb_attachment_max_size_mb: 40,
        kb_import_max_size_mb: 25,
        phone_extract_regex: '',
      }))
      .mockReturnValueOnce(qResult(null))
    apiMock.mockRejectedValueOnce(new Error('patch failed'))

    const Component = (await import('../../src/pages/admin/tabs/SystemTab.vue')).default
    const wrapper = mount(Component, { global: globalPlugins })
    await flushPromises()

    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()

    expect(messageMock.error).toHaveBeenCalled()
  })
})
