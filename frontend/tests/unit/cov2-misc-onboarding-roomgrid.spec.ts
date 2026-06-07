import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref, nextTick } from 'vue'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: { template: '<button @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'disabled', 'loading'], emits: ['click'] },
  NSpin: { template: '<div class="n-spin" />', props: ['show', 'size'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['type', 'size'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() })),
  useRoute: vi.fn(() => ({ params: {}, query: {}, path: '/', name: 'home' })),
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

const authStoreState = {
  user: null as any,
}

const onboardingStoreState = {
  onboardingSteps: [] as Array<{ id: string; title: string; body: string; selector?: string; is_new?: boolean }>,
  loaded: true,
  onboardingEnabled: true,
  onboardingResetTrigger: 'r1',
  load: vi.fn().mockResolvedValue(undefined),
}

const patchMyPreferences = vi.fn().mockResolvedValue(undefined)

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => authStoreState,
}))

vi.mock('../../src/stores/onboarding', () => ({
  useOnboardingSettingsStore: () => onboardingStoreState,
}))

vi.mock('../../src/api/users', () => ({
  patchMyPreferences: (...args: unknown[]) => patchMyPreferences(...args),
}))

const isMobileRef = ref(false)
vi.mock('../../src/composables/useBreakpoints', () => ({
  useBreakpoints: () => ({ isMobile: isMobileRef }),
}))

const globalPlugins = {
  plugins: [i18n],
  stubs: {
    RouterLink: { template: '<a><slot /></a>' },
    BookingCard: {
      template: '<div class="booking-card" @click="$emit(\'click\')" />',
      props: ['booking', 'slotHeight', 'startHour', 'pixelsPerMinute', 'roomTimezone'],
      emits: ['click'],
    },
    Teleport: true,
  },
}

function localToday(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

describe('OnboardingTour.vue', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    patchMyPreferences.mockClear()
    onboardingStoreState.load.mockClear()
    authStoreState.user = {
      id: 'u1',
      preferences: { onboarding_completed: false, onboarding_seen_step_ids: [] },
    }
    onboardingStoreState.onboardingEnabled = true
    onboardingStoreState.loaded = true
    onboardingStoreState.onboardingResetTrigger = 'reset-A'
    onboardingStoreState.onboardingSteps = [
      { id: 's1', title: 'Step 1', body: 'Body 1', selector: '#missing' },
      { id: 's2', title: 'Step 2', body: 'Body 2', selector: '#missing-2', is_new: true },
    ]
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('auto-starts for incomplete onboarding and finishes through primary button', async () => {
    const OnboardingTour = (await import('../../src/components/OnboardingTour.vue')).default
    const wrapper = mount(OnboardingTour, { global: globalPlugins })

    vi.advanceTimersByTime(900)
    await nextTick()
    await flushPromises()

    expect(wrapper.find('.tour-overlay').exists()).toBe(true)
    expect(wrapper.find('.tour-highlight').exists()).toBe(false)

    await wrapper.find('.tour-btn--primary').trigger('click')
    await wrapper.find('.tour-btn--primary').trigger('click')
    await flushPromises()

    expect(patchMyPreferences).toHaveBeenCalledWith({
      onboarding_completed: true,
      onboarding_seen_step_ids: ['s1', 's2'],
    })
    expect(localStorage.getItem('portal-onboarding-done')).toBe('1')
    expect(wrapper.find('.tour-overlay').exists()).toBe(false)
  })

  it('runs delta mode from exposed API and saves seen ids without completion flag', async () => {
    const OnboardingTour = (await import('../../src/components/OnboardingTour.vue')).default
    const wrapper = mount(OnboardingTour, { global: globalPlugins })

    ;(wrapper.vm as unknown as { startDeltaTour: (ids: string[]) => void }).startDeltaTour(['s2'])
    await nextTick()

    expect(wrapper.find('.tour-overlay').exists()).toBe(true)
    await wrapper.find('.tour-skip').trigger('click')
    await flushPromises()

    expect(patchMyPreferences).toHaveBeenCalledWith({ onboarding_seen_step_ids: ['s2'] })
  })

  it('does not auto-start when onboarding is disabled', async () => {
    onboardingStoreState.onboardingEnabled = false
    const OnboardingTour = (await import('../../src/components/OnboardingTour.vue')).default
    const wrapper = mount(OnboardingTour, { global: globalPlugins })

    vi.advanceTimersByTime(900)
    await nextTick()

    expect(wrapper.find('.tour-overlay').exists()).toBe(false)
  })
})

describe('RoomGrid.vue', () => {
  const baseProps = {
    rooms: [
      { id: 'r2', name: 'Room 2', sort_order: 2, timezone: 'UTC', is_active: true, kind: 'physical' },
      { id: 'r1', name: 'Room 1', sort_order: 1, timezone: 'UTC', is_active: true, kind: 'physical' },
    ],
    bookings: [],
    startHour: 8,
    endHour: 10,
  }

  it('renders now-line only for current local date', async () => {
    vi.setSystemTime(new Date('2026-06-07T09:00:00'))
    const RoomGrid = (await import('../../src/components/meetings/RoomGrid.vue')).default

    const todayWrap = mount(RoomGrid, {
      props: { ...baseProps, date: localToday() } as never,
      global: globalPlugins,
    })
    expect(todayWrap.find('.room-grid__now-line').exists()).toBe(true)

    const oldWrap = mount(RoomGrid, {
      props: { ...baseProps, date: '2000-01-01' } as never,
      global: globalPlugins,
    })
    expect(oldWrap.find('.room-grid__now-line').exists()).toBe(false)
  })

  it('emits slot-click from keyboard and grid click, but ignores clicks on booking cards', async () => {
    const RoomGrid = (await import('../../src/components/meetings/RoomGrid.vue')).default
    const wrapper = mount(RoomGrid, {
      props: {
        ...baseProps,
        date: localToday(),
        bookings: [{ id: 'b1', rooms: [{ id: 'r1' }], start_at: '', end_at: '' }],
      } as never,
      global: globalPlugins,
    })

    const firstCells = wrapper.findAll('.room-grid__cells')[0]
    await firstCells.trigger('keydown.enter')

    const el = firstCells.element as HTMLElement
    Object.defineProperty(el, 'getBoundingClientRect', {
      value: () => ({ top: 0, left: 0, width: 200, height: 200, right: 200, bottom: 200, x: 0, y: 0, toJSON: () => ({}) }),
      configurable: true,
    })

    el.dispatchEvent(new MouseEvent('click', { bubbles: true, clientY: 20 }))
    await nextTick()

    const bookingEl = wrapper.find('.booking-card').element as HTMLElement
    bookingEl.dispatchEvent(new MouseEvent('click', { bubbles: true, clientY: 20 }))
    await nextTick()

    const emitted = wrapper.emitted('slot-click') ?? []
    expect(emitted.length).toBe(2)
    expect(emitted[0][0]).toMatchObject({ roomId: 'r1' })
  })

  it('shows mobile indicator when mobile mode is active and more than one room exists', async () => {
    isMobileRef.value = true
    const RoomGrid = (await import('../../src/components/meetings/RoomGrid.vue')).default
    const wrapper = mount(RoomGrid, {
      props: { ...baseProps, date: localToday() } as never,
      global: globalPlugins,
    })

    expect(wrapper.find('.room-grid__indicator').exists()).toBe(true)
    isMobileRef.value = false
  })
})
