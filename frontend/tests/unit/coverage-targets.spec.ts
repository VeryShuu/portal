import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const apiMock = vi.fn()
vi.mock('../../src/api', () => ({
  api: (...args: unknown[]) => apiMock(...args),
}))

describe('src/utils/mapMeetingsError', () => {
  it('returns null for non-object input', async () => {
    const { mapMeetingsError } = await import('../../src/utils/mapMeetingsError')
    expect(mapMeetingsError(null)).toBeNull()
    expect(mapMeetingsError(undefined)).toBeNull()
    expect(mapMeetingsError('boom')).toBeNull()
    expect(mapMeetingsError(42)).toBeNull()
  })

  it('detects START_TIME_IN_PAST via data.code', async () => {
    const { mapMeetingsError } = await import('../../src/utils/mapMeetingsError')
    expect(mapMeetingsError({ data: { code: 'START_TIME_IN_PAST' } })).toBe(
      'START_TIME_IN_PAST',
    )
  })

  it('detects BOOKING_CONFLICT via conflicts array', async () => {
    const { mapMeetingsError } = await import('../../src/utils/mapMeetingsError')
    expect(mapMeetingsError({ data: { conflicts: [{ room_id: 'x' }] } })).toBe(
      'BOOKING_CONFLICT',
    )
  })

  it('detects START_TIME_IN_PAST from pydantic detail msg', async () => {
    const { mapMeetingsError } = await import('../../src/utils/mapMeetingsError')
    const err = { data: { detail: [{ msg: 'value [START_TIME_IN_PAST] here' }] } }
    expect(mapMeetingsError(err)).toBe('START_TIME_IN_PAST')
  })

  it('detects END_BEFORE_START from pydantic detail msg', async () => {
    const { mapMeetingsError } = await import('../../src/utils/mapMeetingsError')
    const err = { data: { detail: [{ msg: 'end_time must be after start_time' }] } }
    expect(mapMeetingsError(err)).toBe('END_BEFORE_START')
  })

  it('skips non-string msg entries and returns null when nothing matches', async () => {
    const { mapMeetingsError } = await import('../../src/utils/mapMeetingsError')
    const err = { data: { detail: [{ msg: 123 }, { other: true }, {}] } }
    expect(mapMeetingsError(err)).toBeNull()
  })

  it('returns null when detail is not an array', async () => {
    const { mapMeetingsError } = await import('../../src/utils/mapMeetingsError')
    expect(mapMeetingsError({ data: { detail: 'nope' } })).toBeNull()
  })
})

describe('src/utils/photoShareUrls', () => {
  it('buildPhotoShareUrl uses window origin by default', async () => {
    const { buildPhotoShareUrl } = await import('../../src/utils/photoShareUrls')
    expect(buildPhotoShareUrl('abc123')).toBe(
      `${window.location.origin}/p/abc123`,
    )
  })

  it('buildPhotoShareUrl respects explicit base', async () => {
    const { buildPhotoShareUrl } = await import('../../src/utils/photoShareUrls')
    expect(buildPhotoShareUrl('tok', 'https://portal.example')).toBe(
      'https://portal.example/p/tok',
    )
  })

  it('buildFolderShareUrl builds public folder url', async () => {
    const { buildFolderShareUrl } = await import('../../src/utils/photoShareUrls')
    expect(buildFolderShareUrl('ftok', 'https://portal.example')).toBe(
      'https://portal.example/photos/public/ftok',
    )
  })

  it('buildFolderShareUrl uses window origin by default', async () => {
    const { buildFolderShareUrl } = await import('../../src/utils/photoShareUrls')
    expect(buildFolderShareUrl('ftok')).toBe(
      `${window.location.origin}/photos/public/ftok`,
    )
  })
})

describe('src/utils/tourTargets', () => {
  it('getTourTargetOptions maps every target with resolved labels', async () => {
    const { getTourTargetOptions, TOUR_TARGETS } = await import(
      '../../src/utils/tourTargets'
    )
    const options = getTourTargetOptions()
    expect(options).toHaveLength(TOUR_TARGETS.length)
    for (const opt of options) {
      expect(typeof opt.label).toBe('string')
      expect(typeof opt.group).toBe('string')
      expect(opt.value).toBe(opt.selector)
    }
  })

  it('tourTargetLabelFor returns a label for a known selector', async () => {
    const { tourTargetLabelFor, TOUR_TARGETS } = await import(
      '../../src/utils/tourTargets'
    )
    const known = TOUR_TARGETS[0].selector
    expect(tourTargetLabelFor(known)).toBeTruthy()
  })

  it('tourTargetLabelFor returns null for an unknown selector', async () => {
    const { tourTargetLabelFor } = await import('../../src/utils/tourTargets')
    expect(tourTargetLabelFor('.no-such-selector')).toBeNull()
  })
})

describe('src/stores/onboarding', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiMock.mockReset()
  })

  it('defaultOnboardingSteps returns four steps with required fields', async () => {
    const { defaultOnboardingSteps } = await import('../../src/stores/onboarding')
    const steps = defaultOnboardingSteps()
    expect(steps).toHaveLength(4)
    for (const step of steps) {
      expect(step.id).toBeTruthy()
      expect(step.selector).toBeTruthy()
      expect(typeof step.title).toBe('string')
      expect(typeof step.body).toBe('string')
      expect(step.is_new).toBe(false)
    }
  })

  it('exposes defaults before loading', async () => {
    const { useOnboardingSettingsStore } = await import('../../src/stores/onboarding')
    const store = useOnboardingSettingsStore()
    expect(store.loaded).toBe(false)
    expect(store.onboardingEnabled).toBe(true)
    expect(store.onboardingResetTrigger).toBe('')
    expect(store.hasCustomSteps).toBe(false)
    expect(store.onboardingSteps).toHaveLength(4)
  })

  it('load() merges API payload into settings', async () => {
    const { useOnboardingSettingsStore } = await import('../../src/stores/onboarding')
    apiMock.mockResolvedValueOnce({
      onboarding_enabled: false,
      onboarding_reset_trigger: 'v2',
      onboarding_steps: [
        { id: 'a', selector: '.x', title: 'T', body: 'B', is_new: true },
      ],
    })
    const store = useOnboardingSettingsStore()
    await store.load()
    expect(apiMock).toHaveBeenCalledWith('/portal/onboarding')
    expect(store.loaded).toBe(true)
    expect(store.onboardingEnabled).toBe(false)
    expect(store.onboardingResetTrigger).toBe('v2')
    expect(store.hasCustomSteps).toBe(true)
    expect(store.onboardingSteps).toHaveLength(1)
  })

  it('load() swallows API errors and still marks loaded', async () => {
    const { useOnboardingSettingsStore } = await import('../../src/stores/onboarding')
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    apiMock.mockRejectedValueOnce(new Error('network'))
    const store = useOnboardingSettingsStore()
    await store.load()
    expect(store.loaded).toBe(true)
    expect(store.onboardingEnabled).toBe(true)
    expect(spy).toHaveBeenCalled()
    spy.mockRestore()
  })

  it('setSettings merges partial data over current state', async () => {
    const { useOnboardingSettingsStore } = await import('../../src/stores/onboarding')
    const store = useOnboardingSettingsStore()
    store.setSettings({ onboarding_enabled: false })
    expect(store.loaded).toBe(true)
    expect(store.onboardingEnabled).toBe(false)
    expect(store.onboardingResetTrigger).toBe('')
  })
})
