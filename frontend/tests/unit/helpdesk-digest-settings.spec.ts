import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

// ── Mock useQuery/useMutation: возвращаем реактивные data/isPending, как реальный хук ─
const { useQueryMock, useMutationMock, queryClientMock, messageMock } = vi.hoisted(() => ({
  useQueryMock: vi.fn(),
  useMutationMock: vi.fn(),
  queryClientMock: { invalidateQueries: vi.fn().mockResolvedValue(undefined) },
  messageMock: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: useQueryMock,
  useMutation: useMutationMock,
  useQueryClient: () => queryClientMock,
}))

vi.mock('naive-ui', () => ({
  NSpin: { template: '<div class="n-spin"><slot /></div>', props: ['show'] },
  NForm: { template: '<form><slot /></form>' },
  NFormItem: { template: '<div class="n-form-item"><slot /></div>', props: ['label'] },
  NInputNumber: {
    template: '<input type="number" :value="value" @input="$emit(\'update:value\', Number($event.target.value))" />',
    props: ['value', 'min', 'max', 'showButton'],
    emits: ['update:value'],
  },
  NSelect: {
    template: '<select :value="value" @change="$emit(\'update:value\', $event.target.value)"><option v-for="o in options" :key="o.value" :value="o.value">{{ o.label }}</option></select>',
    props: ['value', 'options'],
    emits: ['update:value'],
  },
  NCheckbox: {
    template: '<input type="checkbox" :checked="checked" @change="$emit(\'update:checked\', $event.target.checked)" />',
    props: ['checked'],
    emits: ['update:checked'],
  },
  NButton: {
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'disabled', 'loading'],
    emits: ['click'],
  },
  useMessage: () => messageMock,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

function setupQuery(out: object | undefined, isLoading = false) {
  useQueryMock.mockReturnValue({
    data: ref(out),
    isLoading: ref(isLoading),
  })
  const mutateAsync = vi.fn().mockResolvedValue(undefined)
  useMutationMock.mockReturnValue({ mutateAsync, isPending: ref(false) })
  return mutateAsync
}

describe('HelpdeskDigestSettings.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('mounts and renders form fields from query data', async () => {
    setupQuery({
      enabled: true,
      digest_hour: 5,
      digest_minute: 0,
      digest_schedule: 'daily',
      updated_at: '2026-08-03T08:00:00Z',
    })
    const wrapper = mount(
      (await import('../../src/components/admin/HelpdeskDigestSettings.vue')).default,
      {},
    )
    await flushPromises()
    expect(wrapper.find('form').exists()).toBe(true)
    // Час предзаполнен из ответа (5).
    const hourInput = wrapper.find('input[type="number"]')
    expect((hourInput.element as HTMLInputElement).value).toBe('5')
  })

  it('Save button is disabled when form is not dirty', async () => {
    setupQuery({
      enabled: true,
      digest_hour: 8,
      digest_minute: 0,
      digest_schedule: 'weekdays',
      updated_at: null,
    })
    const wrapper = mount(
      (await import('../../src/components/admin/HelpdeskDigestSettings.vue')).default,
      {},
    )
    await flushPromises()
    const saveBtn = wrapper.find('button')
    expect(saveBtn.attributes('disabled')).toBeDefined()
  })

  it('Save calls mutateAsync with the form DTO and shows success message', async () => {
    const mutateAsync = setupQuery({
      enabled: false,
      digest_hour: 8,
      digest_minute: 0,
      digest_schedule: 'weekdays',
      updated_at: null,
    })
    const wrapper = mount(
      (await import('../../src/components/admin/HelpdeskDigestSettings.vue')).default,
      {},
    )
    await flushPromises()
    // Меняем час → форма становится dirty.
    await wrapper.find('input[type="number"]').setValue(5)
    const saveBtn = wrapper.find('button')
    expect(saveBtn.attributes('disabled')).toBeUndefined()
    await saveBtn.trigger('click')
    await flushPromises()
    expect(mutateAsync).toHaveBeenCalledWith({
      enabled: false,
      digest_hour: 5,
      digest_minute: 0,
      digest_schedule: 'weekdays',
    })
    expect(messageMock.success).toHaveBeenCalledWith('admin.modules.saved')
  })

  it('shows error message on save failure', async () => {
    const mutateAsync = vi.fn().mockRejectedValue(new Error('boom'))
    useQueryMock.mockReturnValue({ data: ref(undefined), isLoading: ref(false) })
    useMutationMock.mockReturnValue({ mutateAsync, isPending: ref(false) })
    // Подманим форму вручную: после mount форма null (data undefined → n-spin без формы),
    // поэтому подадим данные для появления формы.
    useQueryMock.mockReturnValue({
      data: ref({ enabled: true, digest_hour: 8, digest_minute: 0, digest_schedule: 'weekdays', updated_at: null }),
      isLoading: ref(false),
    })
    const wrapper = mount(
      (await import('../../src/components/admin/HelpdeskDigestSettings.vue')).default,
      {},
    )
    await flushPromises()
    await wrapper.find('input[type="number"]').setValue(9)
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(messageMock.error).toHaveBeenCalled()
  })
})
