import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const fetchPermissions = vi.fn()
const savePermission = vi.fn()
const deletePermission = vi.fn()
const updateInheritance = vi.fn()
const searchKbUsers = vi.fn()
const messageSuccess = vi.fn()
const messageError = vi.fn()

vi.mock('naive-ui', () => ({
  NModal: {
    template: '<div v-if="show" class="n-modal"><slot /></div>',
    props: ['show', 'modelValue', 'preset', 'title'],
    emits: ['update:show', 'update:modelValue'],
  },
  NSwitch: {
    template: '<input class="n-switch" type="checkbox" :checked="value" @change="$emit(\'update:value\', $event.target.checked)" />',
    props: ['value'],
    emits: ['update:value'],
  },
  NSelect: {
    name: 'NSelect',
    template: '<select class="n-select" @change="$emit(\'update:value\', $event.target.value)"><slot /></select>',
    props: ['value', 'options', 'size'],
    emits: ['update:value'],
  },
  NButton: {
    template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled', 'text'],
    emits: ['click'],
  },
  NAutoComplete: {
    name: 'NAutoComplete',
    template: '<input class="n-auto-complete" :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'options', 'loading', 'placeholder', 'clearable', 'size'],
    emits: ['update:value', 'select'],
  },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['size', 'type', 'bordered'] },
  useMessage: () => ({ success: messageSuccess, error: messageError, warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {} })),
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

vi.mock('../../src/api/kb', () => ({
  fetchPermissions: (...args: unknown[]) => fetchPermissions(...args),
  savePermission: (...args: unknown[]) => savePermission(...args),
  deletePermission: (...args: unknown[]) => deletePermission(...args),
  updateInheritance: (...args: unknown[]) => updateInheritance(...args),
  searchKbUsers: (...args: unknown[]) => searchKbUsers(...args),
}))

vi.mock('@/utils/parseApiError', () => ({
  parseApiError: vi.fn(() => 'parse-error'),
}))

describe('cov2 KbPermissionsModal.vue', () => {
  beforeEach(() => {
    fetchPermissions.mockReset()
    savePermission.mockReset()
    deletePermission.mockReset()
    updateInheritance.mockReset()
    searchKbUsers.mockReset()
    messageSuccess.mockReset()
    messageError.mockReset()

    fetchPermissions.mockResolvedValue({
      items: [
        { id: 'p1', subject_type: 'user', subject_id: 'u1', subject_name: 'User One', email: 'u1@x.test', permission: 'viewer', is_creator: false },
        { id: 'p2', subject_type: 'group', subject_id: 'g1', subject_name: 'Group One', permission: 'editor', is_creator: true },
      ],
    })
    savePermission.mockResolvedValue({})
    deletePermission.mockResolvedValue({})
    updateInheritance.mockResolvedValue({})
    searchKbUsers.mockResolvedValue([
      { subject_type: 'user', subject_id: 'u9', subject_name: 'User Nine', email: 'u9@x.test' },
    ])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads permissions on open and renders inherit toggle for article', async () => {
    const Cmp = (await import('../../src/components/KbPermissionsModal.vue')).default
    const w = mount(Cmp, {
      props: {
        modelValue: true,
        resourceType: 'article',
        resourceId: 'art-1',
        inheritPermissions: true,
      },
      global: { plugins: [i18n] },
    })

    await flushPromises()
    expect(w.exists()).toBe(true)
    expect(fetchPermissions).toHaveBeenCalledWith('article', 'art-1')
    expect(w.find('.n-switch').exists()).toBe(true)
    expect(w.findAll('.perm-row').length).toBe(2)
  })

  it('updates permission and deletes permission row actions', async () => {
    const Cmp = (await import('../../src/components/KbPermissionsModal.vue')).default
    const w = mount(Cmp, {
      props: {
        modelValue: true,
        resourceType: 'section',
        resourceId: 'sec-1',
      },
      global: { plugins: [i18n] },
    })

    await flushPromises()

    const selects = w.findAllComponents({ name: 'NSelect' })
    await selects[0].vm.$emit('update:value', 'manager')
    await flushPromises()
    expect(savePermission).toHaveBeenCalledWith('section', 'sec-1', expect.objectContaining({ subject_id: 'u1', permission: 'manager' }))

    await w.find('.perm-row .n-button').trigger('click')
    await flushPromises()
    expect(deletePermission).toHaveBeenCalledWith('section', 'sec-1', 'u1')
    expect(messageSuccess).toHaveBeenCalled()
  })

  it('searches subjects with debounce, selects one, and adds permission', async () => {
    vi.useFakeTimers()
    const Cmp = (await import('../../src/components/KbPermissionsModal.vue')).default
    const w = mount(Cmp, {
      props: {
        modelValue: true,
        resourceType: 'article',
        resourceId: 'art-2',
        inheritPermissions: false,
      },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    const ac = w.findComponent({ name: 'NAutoComplete' })
    await ac.vm.$emit('update:value', 'u')
    vi.advanceTimersByTime(450)
    await flushPromises()
    expect(searchKbUsers).not.toHaveBeenCalled()

    await ac.vm.$emit('update:value', 'user')
    vi.advanceTimersByTime(450)
    await flushPromises()
    expect(searchKbUsers).toHaveBeenCalled()

    await ac.vm.$emit('select', 'u9')
    await flushPromises()

    const addBtn = w.findAll('button.n-button').find((b) => b.text().includes('kb.permissions.add'))
    await addBtn!.trigger('click')
    await flushPromises()

    expect(savePermission).toHaveBeenCalledWith('article', 'art-2', expect.objectContaining({ subject_id: 'u9' }))
    expect(messageSuccess).toHaveBeenCalled()
  })

  it('handles inherit toggle failure and close reset branch', async () => {
    updateInheritance.mockRejectedValueOnce(new Error('x'))

    const Cmp = (await import('../../src/components/KbPermissionsModal.vue')).default
    const w = mount(Cmp, {
      props: {
        modelValue: true,
        resourceType: 'article',
        resourceId: 'art-3',
        inheritPermissions: true,
      },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    await w.find('.n-switch').setValue(false)
    await flushPromises()
    expect(messageError).toHaveBeenCalled()

    await w.setProps({ modelValue: false })
    await flushPromises()
    expect(w.find('.n-auto-complete').exists()).toBe(false)
  })
})
