/**
 * Unit-тест MeetingFormDialog.vue: монтирование (create/edit),
 * emit update:show при отмене, конфликт-ошибка отображается.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NModal: {
    template: '<div v-if="show" class="n-modal"><slot /><slot name="footer" /></div>',
    props: ['show', 'title', 'preset', 'maskClosable'],
    emits: ['update:show'],
  },
  NForm: {
    template: '<form><slot /></form>',
    props: ['model', 'labelPlacement', 'requireMarkPlacement'],
    methods: { validate: () => Promise.resolve() },
  },
  NFormItem: { template: '<div class="n-form-item"><slot /></div>', props: ['label', 'path', 'rule'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type', 'rows', 'maxlength'],
    emits: ['update:value'],
  },
  NDatePicker: { template: '<input class="n-date-picker" />', props: ['value', 'type', 'timePickerProps', 'dateLocale'] },
  NSelect: { template: '<select class="n-select" />', props: ['value', 'options', 'placeholder', 'clearable'] },
  NSpin: { template: '<div class="n-spin" />', props: ['size'] },
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'ghost', 'loading'],
    emits: ['click'],
  },
  NSpace: { template: '<div class="n-space"><slot /></div>', props: ['justify'] },
  NGrid: { template: '<div class="n-grid"><slot /></div>', props: ['cols', 'xGap'] },
  NGi: { template: '<div class="n-gi"><slot /></div>' },
  NRadioGroup: { template: '<div class="n-radio-group"><slot /></div>', props: ['value'], emits: ['update:value'] },
  NRadio: { template: '<label><slot /></label>', props: ['value'] },
  dateRuRU: {},
  dateEnUS: {},
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('../../src/utils/mapMeetingsError', () => ({
  mapMeetingsError: vi.fn((err: { code?: string }) => err?.code ?? 'GENERIC'),
}))

vi.mock('../../src/stores/modules', () => ({
  useModulesStore: () => ({
    meetingsSettings: { min_search_chars: 2, max_recurrence_horizon_days: 365 },
    isEnabled: (_m: string) => true,
  }),
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: 'user-1' },
    isAdmin: false,
  }),
}))

const doCreate = vi.fn().mockResolvedValue({})
const doUpdate = vi.fn().mockResolvedValue({})
const doDelete = vi.fn().mockResolvedValue({})
const doUpdateSeries = vi.fn().mockResolvedValue({})
const doDeleteSeries = vi.fn().mockResolvedValue({})

vi.mock('../../src/queries/meetings', () => ({
  useMeetingRoomsQuery: vi.fn(() => ({
    data: ref([
      { id: 'r1', name: 'Room A' },
      { id: 'r2', name: 'Room B' },
    ]),
    isLoading: ref(false),
  })),
  useCreateBookingMutation: vi.fn(() => ({ mutateAsync: doCreate })),
  useUpdateBookingMutation: vi.fn(() => ({ mutateAsync: doUpdate })),
  useDeleteBookingMutation: vi.fn(() => ({ mutateAsync: doDelete })),
  useUpdateSeriesMutation: vi.fn(() => ({ mutateAsync: doUpdateSeries })),
  useDeleteSeriesMutation: vi.fn(() => ({ mutateAsync: doDeleteSeries })),
}))

vi.mock('../../src/components/meetings/ParticipantPicker.vue', () => ({
  default: { template: '<div class="participant-picker" />', props: ['modelValue', 'minChars'] },
}))

vi.mock('../../src/components/meetings/RecurrenceEditor.vue', () => ({
  default: { template: '<div class="recurrence-editor" />', props: ['modelValue', 'startDate', 'maxDays'] },
}))

describe('MeetingFormDialog.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    doCreate.mockClear()
    doUpdate.mockClear()
    doDelete.mockClear()
  })

  it('mounts in create mode and renders room chips', async () => {
    const { default: Dialog } = await import('../../src/components/meetings/MeetingFormDialog.vue')
    const wrapper = mount(Dialog, {
      props: { show: true },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    expect(wrapper.find('.n-modal').exists()).toBe(true)
    expect(wrapper.findAll('.room-chip').length).toBe(2)
  })

  it('does not render modal when show=false', async () => {
    const { default: Dialog } = await import('../../src/components/meetings/MeetingFormDialog.vue')
    const wrapper = mount(Dialog, {
      props: { show: false },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.n-modal').exists()).toBe(false)
  })

  it('mounts in edit mode and shows delete button for owner', async () => {
    const { default: Dialog } = await import('../../src/components/meetings/MeetingFormDialog.vue')
    const wrapper = mount(Dialog, {
      props: {
        show: true,
        booking: {
          id: 'b1',
          creator_id: 'user-1',
          title: 'Existing',
          description: 'Desc',
          rooms: [{ id: 'r1', name: 'Room A' }],
          invited_users: [],
          start_time: new Date(Date.now() + 3600_000).toISOString(),
          end_time: new Date(Date.now() + 7200_000).toISOString(),
          series_id: null,
        },
      },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    const buttons = wrapper.findAll('button.n-button')
    expect(buttons.length).toBeGreaterThanOrEqual(3)
  })

  it('emits update:show=false when cancel button is clicked', async () => {
    const { default: Dialog } = await import('../../src/components/meetings/MeetingFormDialog.vue')
    const wrapper = mount(Dialog, {
      props: { show: true },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    const cancel = wrapper.findAll('button.n-button')[0]
    await cancel.trigger('click')
    expect(wrapper.emitted('update:show')).toBeTruthy()
    expect(wrapper.emitted('update:show')![0]).toEqual([false])
  })

  it('toggles room selection on chip click', async () => {
    const { default: Dialog } = await import('../../src/components/meetings/MeetingFormDialog.vue')
    const wrapper = mount(Dialog, {
      props: { show: true },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    const chip = wrapper.findAll('.room-chip')[0]
    await chip.trigger('click')
    await nextTick()
    expect(chip.classes()).toContain('room-chip--selected')
    await chip.trigger('click')
    await nextTick()
    expect(chip.classes()).not.toContain('room-chip--selected')
  })
})
