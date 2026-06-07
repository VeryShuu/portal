import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, h, nextTick, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import type { ClockCity } from '../../src/composables/useWorldClockCities'

const mockConfirm = vi.fn()

const mockMessageSuccess = vi.fn()
const mockMessageWarning = vi.fn()
const mockMessageError = vi.fn()

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('naive-ui', () => ({
  useMessage: () => ({
    success: mockMessageSuccess,
    warning: mockMessageWarning,
    error: mockMessageError,
  }),
}))

vi.mock('../../src/composables/useConfirmDialog', () => ({
  useConfirmDialog: () => ({ confirm: (...args: unknown[]) => mockConfirm(...args) }),
}))

vi.mock('../../src/api/index', () => ({ api: vi.fn() }))

import { useWorldClockForm } from '../../src/composables/useWorldClockForm'

type FormApi = ReturnType<typeof useWorldClockForm>

type HostSetup = {
  api: FormApi
  router: Router
  now: Ref<Date>
  cities: Ref<ClockCity[]>
  add: ReturnType<typeof vi.fn>
  update: ReturnType<typeof vi.fn>
  remove: ReturnType<typeof vi.fn>
  reset: ReturnType<typeof vi.fn>
  reorder: ReturnType<typeof vi.fn>
  isValidTimezone: ReturnType<typeof vi.fn>
  onAfterMutation: ReturnType<typeof vi.fn>
}

async function setupHost(): Promise<HostSetup> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()

  const now = ref(new Date('2026-01-01T10:00:00.000Z'))
  const cities = ref<ClockCity[]>([])
  const add = vi.fn()
  const update = vi.fn()
  const remove = vi.fn()
  const reset = vi.fn()
  const reorder = vi.fn()
  const isValidTimezone = vi.fn((tz: string) => tz === 'Europe/Moscow' || tz === 'UTC')
  const onAfterMutation = vi.fn()

  let api: FormApi | null = null

  const Host = defineComponent({
    setup() {
      api = useWorldClockForm({
        now,
        cities,
        add,
        update,
        remove,
        reset,
        reorder,
        isValidTimezone,
        onAfterMutation,
      })
      return () => h('div')
    },
  })

  mount(Host, { global: { plugins: [router] } })

  return {
    api: api as unknown as FormApi,
    router,
    now,
    cities,
    add,
    update,
    remove,
    reset,
    reorder,
    isValidTimezone,
    onAfterMutation,
  }
}

describe('cov-media useWorldClockForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('exposes timezone options and computes preview time fallback branches', async () => {
    const { api, isValidTimezone } = await setupHost()

    expect(api.tzOptions.value.length).toBeGreaterThan(5)
    expect(api.tzOptions.value.some((o) => o.value === 'UTC')).toBe(true)

    api.form.value.timezone = ''
    expect(api.previewTime.value).toBe('—')

    api.form.value.timezone = 'Bad/TZ'
    expect(api.previewTime.value).toBe('—')

    isValidTimezone.mockReturnValueOnce(true)
    const dtfSpy = vi.spyOn(Intl, 'DateTimeFormat').mockImplementation(() => {
      throw new Error('boom')
    })
    api.form.value.timezone = 'Europe/Moscow'
    expect(api.previewTime.value).toBe('—')
    dtfSpy.mockRestore()
  })

  it('openAdd resets form and openEdit fills from row', async () => {
    const { api } = await setupHost()

    api.openAdd()
    expect(api.modalOpen.value).toBe(true)
    expect(api.editing.value).toBeNull()
    expect(api.form.value).toEqual({ name: '', timezone: '', lat: null, lon: null })

    const row: ClockCity = {
      id: 'c1',
      code: 'MSK',
      name: 'Moscow',
      timezone: 'Europe/Moscow',
      lat: 55.7,
      lon: 37.6,
    }
    api.openEdit(row)

    expect(api.editing.value?.id).toBe('c1')
    expect(api.form.value).toEqual({
      name: 'Moscow',
      timezone: 'Europe/Moscow',
      lat: 55.7,
      lon: 37.6,
    })
    expect(api.modalOpen.value).toBe(true)
  })

  it('onGeocode handles empty query, success, not-found and error', async () => {
    const { api } = await setupHost()

    const fetchSpy = vi.spyOn(globalThis, 'fetch' as never)

    api.form.value.name = '  '
    await api.onGeocode()
    expect(fetchSpy).not.toHaveBeenCalled()

    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ results: [{ latitude: 1.2, longitude: 3.4, timezone: 'UTC' }] }),
    } as Response)

    api.form.value = { name: 'Moscow', timezone: '', lat: null, lon: null }
    await api.onGeocode()

    expect(api.form.value.lat).toBe(1.2)
    expect(api.form.value.lon).toBe(3.4)
    expect(api.form.value.timezone).toBe('UTC')
    expect(mockMessageSuccess).toHaveBeenCalledWith('admin.worldClock.geocodeOk')

    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ results: [] }),
    } as Response)

    await api.onGeocode()
    expect(mockMessageWarning).toHaveBeenCalledWith('admin.worldClock.geocodeNotFound')

    fetchSpy.mockResolvedValueOnce({ ok: false } as Response)
    await api.onGeocode()
    expect(mockMessageError).toHaveBeenCalledWith('admin.worldClock.geocodeError')
    expect(api.geocoding.value).toBe(false)
  })

  it('submit returns on validation failure', async () => {
    const { api, add, update } = await setupHost()

    api.formRef.value = {
      validate: vi.fn().mockRejectedValue(new Error('invalid')),
    }

    await api.submit()

    expect(add).not.toHaveBeenCalled()
    expect(update).not.toHaveBeenCalled()
  })

  it('submit add path creates payload, closes modal and calls onAfterMutation', async () => {
    const { api, add, onAfterMutation } = await setupHost()

    api.openAdd()
    api.form.value = { name: '  london ', timezone: ' UTC ', lat: 1, lon: 2 }
    api.formRef.value = { validate: vi.fn().mockResolvedValue(undefined) }

    await api.submit()
    await nextTick()

    expect(add).toHaveBeenCalledWith({
      name: 'london',
      code: 'LON',
      timezone: 'UTC',
      lat: 1,
      lon: 2,
    })
    expect(mockMessageSuccess).toHaveBeenCalledWith('admin.worldClock.added')
    expect(api.modalOpen.value).toBe(false)
    expect(onAfterMutation).toHaveBeenCalledTimes(1)
  })

  it('submit edit path reuses existing code and calls update', async () => {
    const { api, update, onAfterMutation } = await setupHost()

    const row: ClockCity = {
      id: 'c-edit',
      code: 'MSK',
      name: 'Moscow',
      timezone: 'Europe/Moscow',
      lat: 55,
      lon: 37,
    }

    api.openEdit(row)
    api.form.value = { name: 'Moscow+', timezone: 'Europe/Moscow', lat: 56, lon: 38 }
    api.formRef.value = { validate: vi.fn().mockResolvedValue(undefined) }

    await api.submit()
    await nextTick()

    expect(update).toHaveBeenCalledWith('c-edit', {
      name: 'Moscow+',
      code: 'MSK',
      timezone: 'Europe/Moscow',
      lat: 56,
      lon: 38,
    })
    expect(mockMessageSuccess).toHaveBeenCalledWith('admin.worldClock.saved')
    expect(onAfterMutation).toHaveBeenCalledTimes(1)
  })

  it('onDelete and onReset handle confirm false and true branches', async () => {
    const { api, remove, reset, onAfterMutation } = await setupHost()

    const row: ClockCity = {
      id: 'c-del',
      code: 'DEL',
      name: 'DeleteMe',
      timezone: 'UTC',
    }

    mockConfirm.mockResolvedValueOnce(false)
    await api.onDelete(row)
    expect(remove).not.toHaveBeenCalled()

    mockConfirm.mockResolvedValueOnce(true)
    await api.onDelete(row)
    await nextTick()
    expect(remove).toHaveBeenCalledWith('c-del')
    expect(mockMessageSuccess).toHaveBeenCalledWith('admin.worldClock.deleted')

    mockConfirm.mockResolvedValueOnce(false)
    await api.onReset()
    expect(reset).not.toHaveBeenCalled()

    mockConfirm.mockResolvedValueOnce(true)
    await api.onReset()
    await nextTick()
    expect(reset).toHaveBeenCalledTimes(1)
    expect(mockMessageSuccess).toHaveBeenCalledWith('admin.worldClock.resetDone')
    expect(onAfterMutation).toHaveBeenCalled()
  })
})
