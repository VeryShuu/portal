import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref, defineComponent } from 'vue'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const messageApi = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }

const NDataTableStub = defineComponent({
  name: 'NDataTable',
  props: ['columns', 'data', 'loading', 'pagination', 'remote', 'rowKey'],
  emits: ['update:page'],
  template: '<div class="n-data-table"><span class="rows">{{ (data || []).length }}</span><button class="emit-page" @click="$emit(\'update:page\', 2)">page</button></div>',
})

const formValidateMock = vi.fn().mockResolvedValue(undefined)
const NFormStub = defineComponent({
  name: 'NForm',
  props: ['model', 'rules', 'labelPlacement'],
  setup(_props, { expose }) {
    expose({ validate: formValidateMock })
    return {}
  },
  template: '<form><slot /></form>',
})

vi.mock('naive-ui', () => ({
  NButton: { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'disabled', 'loading', 'ghost'], emits: ['click'] },
  NDataTable: NDataTableStub,
  NModal: { template: '<div class="n-modal" v-if="show"><slot /><slot name="footer" /></div>', props: ['show', 'title', 'preset', 'maskClosable'], emits: ['update:show'] },
  NForm: NFormStub,
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'path', 'rule'] },
  NInput: { template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />', props: ['value', 'placeholder', 'maxlength', 'clearable'], emits: ['update:value'] },
  NSelect: { template: '<select @change="$emit(\'update:value\', $event.target.value)"><option value=""></option></select>', props: ['value', 'options', 'placeholder', 'clearable', 'size'], emits: ['update:value'] },
  NInputNumber: { template: '<input type="number" :value="value" @input="$emit(\'update:value\', Number($event.target.value))" />', props: ['value', 'min', 'max'], emits: ['update:value'] },
  NSwitch: { template: '<input type="checkbox" :checked="value" @change="$emit(\'update:value\', $event.target.checked)" />', props: ['value', 'size'], emits: ['update:value'] },
  NSpace: { template: '<div><slot /></div>', props: ['justify', 'size'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size', 'bordered'] },
  NRadio: { template: '<label><slot /></label>', props: ['value'] },
  NRadioGroup: { template: '<div><slot /></div>', props: ['value'], emits: ['update:value'] },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  useMessage: () => messageApi,
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/admin', name: 'admin' })),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn(() => ({ data: { value: undefined }, isLoading: { value: false }, isFetching: { value: false }, error: { value: null }, refetch: vi.fn() })),
  useMutation: vi.fn(() => ({ mutate: vi.fn(), mutateAsync: vi.fn().mockResolvedValue(undefined), isPending: { value: false }, isError: { value: false } })),
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn(), setQueryData: vi.fn() })),
  useInfiniteQuery: vi.fn(() => ({ data: { value: { pages: [] } }, isLoading: { value: false }, fetchNextPage: vi.fn(), hasNextPage: { value: false } })),
  keepPreviousData: undefined,
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({ data: {} }),
  apiUpload: vi.fn().mockResolvedValue({ data: {} }),
  BASE_URL: '/api/v1',
}))

vi.mock('@vicons/ionicons5', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))
vi.mock('@vicons/fluent', () => new Proxy({}, { get: () => ({ template: '<span />' }) }))

const meetingRoomsQueryMock = vi.fn()
const createRoomMutate = vi.fn().mockResolvedValue(undefined)
const updateRoomMutate = vi.fn().mockResolvedValue(undefined)
const deleteRoomMutate = vi.fn().mockResolvedValue(undefined)

vi.mock('../../src/queries/meetings', () => ({
  useMeetingRoomsQuery: (...args: unknown[]) => meetingRoomsQueryMock(...args),
  useCreateRoomMutation: () => ({ mutateAsync: createRoomMutate }),
  useUpdateRoomMutation: () => ({ mutateAsync: updateRoomMutate }),
  useDeleteRoomMutation: () => ({ mutateAsync: deleteRoomMutate }),
}))

const systemSettingsQueryMock = vi.fn(() => ({ data: ref({ timezone: 'UTC' }) }))

const emailListRef = ref<any>({ items: [], total: 0, counts_30d: null })
const emailLoadingRef = ref(false)
const emailDetailRef = ref<any>(null)
const retryMutate = vi.fn().mockResolvedValue(undefined)
const cancelMutate = vi.fn().mockResolvedValue(undefined)

vi.mock('../../src/queries/admin', () => ({
  useSystemSettingsQuery: (...args: unknown[]) => systemSettingsQueryMock(...args),
  useEmailOutboxQuery: vi.fn(() => ({ data: emailListRef, isLoading: emailLoadingRef })),
  useEmailOutboxItemQuery: vi.fn(() => ({ data: emailDetailRef })),
  useRetryEmailOutboxMutation: vi.fn(() => ({ mutateAsync: retryMutate, isPending: ref(false) })),
  useCancelEmailOutboxMutation: vi.fn(() => ({ mutateAsync: cancelMutate, isPending: ref(false) })),
}))

vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'parsed-error'),
}))

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
  },
}

describe('MeetingRoomsAdminPage.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    messageApi.success.mockClear()
    messageApi.error.mockClear()
    formValidateMock.mockClear()
    formValidateMock.mockResolvedValue(undefined)
    createRoomMutate.mockReset()
    createRoomMutate.mockResolvedValue(undefined)
    meetingRoomsQueryMock.mockReturnValue({
      data: ref([
        { id: 'r1', name: 'Alpha', kind: 'physical', email: null, link: null, timezone: 'UTC', sort_order: 1, is_active: true },
        { id: 'r2', name: 'Beta', kind: 'virtual', email: 'beta@x.com', link: null, timezone: 'UTC', sort_order: 2, is_active: false },
      ]),
      isLoading: ref(false),
    })
  })

  it('renders loaded table and filters inactive rooms when toggle is enabled', async () => {
    const MeetingRoomsAdminPage = (await import('../../src/pages/admin/MeetingRoomsAdminPage.vue')).default
    const wrapper = mount(MeetingRoomsAdminPage, { global: globalPlugins })

    expect(wrapper.find('.n-data-table .rows').text()).toBe('2')
    await wrapper.find('.admin-rooms__filters input[type="checkbox"]').setValue(true)
    await flushPromises()
    expect(wrapper.find('.n-data-table .rows').text()).toBe('1')
  })

  it('opens create form and saves successfully', async () => {
    const MeetingRoomsAdminPage = (await import('../../src/pages/admin/MeetingRoomsAdminPage.vue')).default
    const wrapper = mount(MeetingRoomsAdminPage, { global: globalPlugins })

    await wrapper.find('.admin-rooms__header button').trigger('click')
    expect(wrapper.find('.n-modal').exists()).toBe(true)

    const nameInput = wrapper.find('.n-modal input')
    await nameInput.setValue('New Room')
    const modalButtons = wrapper.findAll('.n-modal button')
    await modalButtons[modalButtons.length - 1].trigger('click')
    await flushPromises()

    expect(createRoomMutate).toHaveBeenCalledTimes(1)
    expect(messageApi.success).toHaveBeenCalled()
  })

  it('shows error message when save fails', async () => {
    createRoomMutate.mockRejectedValueOnce(new Error('fail'))
    const MeetingRoomsAdminPage = (await import('../../src/pages/admin/MeetingRoomsAdminPage.vue')).default
    const wrapper = mount(MeetingRoomsAdminPage, { global: globalPlugins })

    await wrapper.find('.admin-rooms__header button').trigger('click')
    const modalButtons = wrapper.findAll('.n-modal button')
    await modalButtons[modalButtons.length - 1].trigger('click')
    await flushPromises()

    expect(messageApi.error).toHaveBeenCalled()
  })
})

describe('EmailOutboxTab.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    messageApi.success.mockClear()
    messageApi.error.mockClear()
    emailLoadingRef.value = false
    emailDetailRef.value = null
    emailListRef.value = {
      items: [
        {
          id: 'e1',
          status: 'FAILED',
          kind: 'meeting',
          to_email: 'a@x.com',
          subject: 'Subj',
          attempts: 1,
          max_attempts: 3,
          created_at: '2024-01-01T10:00:00Z',
          last_error: 'boom',
          last_error_type: 'x',
          last_error_class: 'y',
        },
      ],
      total: 1,
      counts_30d: { PENDING: 1, SENDING: 0, SENT: 0, FAILED: 1, DLQ: 2, CANCELLED: 0 },
    }
  })

  it('renders stats, dlq alert, and table rows for loaded data', async () => {
    const EmailOutboxTab = (await import('../../src/pages/admin/tabs/EmailOutboxTab.vue')).default
    const wrapper = mount(EmailOutboxTab, { global: globalPlugins })

    expect(wrapper.find('.outbox-stats').exists()).toBe(true)
    expect(wrapper.find('.outbox-dlq-alert').exists()).toBe(true)
    expect(wrapper.find('.n-data-table .rows').text()).toBe('1')
  })

  it('mounts in loading scenario and hides stats when counts are absent', async () => {
    emailLoadingRef.value = true
    emailListRef.value = { items: [], total: 0, counts_30d: null }

    const EmailOutboxTab = (await import('../../src/pages/admin/tabs/EmailOutboxTab.vue')).default
    const wrapper = mount(EmailOutboxTab, { global: globalPlugins })

    expect(wrapper.find('.outbox-stats').exists()).toBe(false)
    expect(wrapper.find('.n-data-table').exists()).toBe(true)
  })
})
