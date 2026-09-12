import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const messageApi = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }

vi.mock('naive-ui', () => ({
  NButton: { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'loading'], emits: ['click'] },
  NFormItem: { template: '<div><slot /></div>', props: ['label', 'showFeedback'] },
  NInputNumber: { template: '<input type="number" :value="value" />', props: ['value', 'min', 'max'] },
  NSwitch: {
    template: '<input type="checkbox" class="n-switch" :checked="value" @change="$emit(\'update:value\', $event.target.checked)" />',
    props: ['value'],
    emits: ['update:value'],
  },
  useMessage: () => messageApi,
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
  createRouter: vi.fn(),
  createWebHistory: vi.fn(),
}))

vi.mock('../../src/router', () => ({
  ROUTES: { MEETINGS_ROOMS: '/admin/meeting-rooms' },
  default: {},
}))

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
}))

const apiMock = vi.fn().mockResolvedValue({})

vi.mock('../../src/api', () => ({
  api: (...args: unknown[]) => apiMock(...(args as [])),
}))

const modulesData = ref<unknown>(null)

vi.mock('../../src/queries/admin', () => ({
  useModulesAdminQuery: () => ({ data: modulesData }),
  queryKeys: {},
}))

import MeetingsModuleSettings from '../../src/components/admin/MeetingsModuleSettings.vue'

const meetingsSettings = (rsvp: boolean) => ({
  meetings: {
    enabled: true,
    calendar_start_hour: 8,
    calendar_end_hour: 19,
    max_recurrence_horizon_days: 31,
    min_search_chars: 3,
    rsvp_ingest_enabled: rsvp,
  },
})

const mountSettings = () =>
  mount(MeetingsModuleSettings, { global: { plugins: [i18n] } })

describe('MeetingsModuleSettings.vue — RSVP ingest switch', () => {
  beforeEach(() => {
    apiMock.mockClear()
    messageApi.success.mockClear()
  })

  it('reflects rsvp_ingest_enabled from the admin query', async () => {
    modulesData.value = meetingsSettings(true)
    const w = mountSettings()
    await flushPromises()
    const sw = w.find('.n-switch')
    expect(sw.exists()).toBe(true)
    expect((sw.element as HTMLInputElement).checked).toBe(true)
  })

  it('saves rsvp_ingest_enabled in the PUT body', async () => {
    modulesData.value = meetingsSettings(true)
    const w = mountSettings()
    await flushPromises()

    await w.findAll('button').at(-1)!.trigger('click')
    await flushPromises()

    expect(apiMock).toHaveBeenCalledTimes(1)
    const [url, init] = apiMock.mock.calls[0] as [string, { method: string, body: unknown }]
    expect(url).toBe('/admin/modules/meetings')
    expect(init.method).toBe('PUT')
    const body = (typeof init.body === 'string' ? JSON.parse(init.body) : init.body) as Record<string, unknown>
    expect(body.rsvp_ingest_enabled).toBe(true)
    expect(messageApi.success).toHaveBeenCalled()
  })
})
