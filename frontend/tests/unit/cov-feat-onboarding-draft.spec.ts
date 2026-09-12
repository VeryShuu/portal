import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

const api = vi.fn()
const invalidateQueries = vi.fn()
const setSettings = vi.fn()
const message = { success: vi.fn(), error: vi.fn() }

const settingsData = ref<any>(null)

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string, p?: any) => (p ? `${k}:${JSON.stringify(p)}` : k), locale: ref('en') }),
}))

vi.mock('naive-ui', () => ({
  useMessage: () => message,
}))

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: () => ({ invalidateQueries }),
}))

vi.mock('../../src/api/index', () => ({ api }))

vi.mock('../../src/queries/admin', () => ({
  useSystemSettingsQuery: () => ({ data: settingsData }),
}))

vi.mock('../../src/queries/keys', () => ({
  queryKeys: { admin: { systemSettings: () => ['admin', 'systemSettings'] } },
}))

vi.mock('../../src/stores/onboarding', () => ({
  defaultOnboardingSteps: () => [
    { id: 'd1', selector: '#one', title: 'One', body: '', is_new: false },
    { id: 'd2', selector: '#two', title: 'Two', body: '', is_new: true },
  ],
  useOnboardingSettingsStore: () => ({
    onboardingEnabled: true,
    setSettings,
  }),
}))

vi.mock('../../src/utils/tourTargets', () => ({
  getTourTargetOptions: () => [
    { group: 'Header', label: 'Logo', value: '#logo' },
    { group: 'Header', label: 'Menu', value: '#menu' },
    { group: 'Main', label: 'Card', value: '#card' },
  ],
  tourTargetLabelFor: (v: string) => (v === '#logo' ? 'Logo' : null),
}))

async function setupHost() {
  let state: any = null
  const mod = await import('../../src/components/admin/onboarding/composables/useOnboardingDraft')
  const Host = defineComponent({
    setup() {
      state = mod.useOnboardingDraft()
      return () => h('div')
    },
  })
  mount(Host)
  await nextTick()
  return { state, mod }
}

describe('cov-feat useOnboardingDraft', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    settingsData.value = null
  })

  it('exports makeKey and toFormRow', async () => {
    const mod = await import('../../src/components/admin/onboarding/composables/useOnboardingDraft')
    const key1 = mod.makeKey()
    const key2 = mod.makeKey()
    expect(key1).not.toBe(key2)

    const row = mod.toFormRow({ id: 'a', selector: '#s', title: 'T', body: undefined, is_new: false } as any)
    expect(row.id).toBe('a')
    expect(row.body).toBe('')
    expect(row._key).toContain('row-')
  })

  it('syncs from server with override and default branches', async () => {
    settingsData.value = {
      onboarding_enabled: false,
      onboarding_reset_trigger: '2026-01-01T00:00:00.000Z',
      onboarding_steps: [{ id: 'c1', selector: '#logo', title: 'Custom', body: 'b', is_new: true }],
    }
    const { state } = await setupHost()
    expect(state.form.onboarding_enabled).toBe(false)
    expect(state.hasCustom.value).toBe(true)
    expect(state.stepsForm.value[0].title).toBe('Custom')

    settingsData.value = {
      onboarding_enabled: true,
      onboarding_reset_trigger: '',
      onboarding_steps: null,
    }
    state.stepsDirty.value = false
    await nextTick()
    expect(state.hasCustom.value).toBe(false)
    expect(state.stepsForm.value.length).toBe(2)
  })

  it('does not sync when steps are dirty and supports local list operations', async () => {
    settingsData.value = {
      onboarding_enabled: true,
      onboarding_reset_trigger: '',
      onboarding_steps: [{ id: 'c1', selector: '#logo', title: 'A', body: '', is_new: false }],
    }
    const { state } = await setupHost()

    state.stepsForm.value[0].title = 'Changed'
    await nextTick()
    expect(state.stepsDirty.value).toBe(true)

    settingsData.value = {
      onboarding_enabled: true,
      onboarding_reset_trigger: '',
      onboarding_steps: [{ id: 'c2', selector: '#menu', title: 'FromServer', body: '', is_new: false }],
    }
    await nextTick()
    expect(state.stepsForm.value[0].title).toBe('Changed')

    state.addStep()
    expect(state.stepsForm.value.length).toBe(2)
    state.moveStep(0, 1)
    expect(state.stepsForm.value[1].title).toBe('Changed')
    state.moveStep(0, -1)
    state.removeStep(1)
    expect(state.stepsForm.value.length).toBe(1)
  })

  it('builds target options and label/tag renderers', async () => {
    settingsData.value = { onboarding_enabled: true, onboarding_reset_trigger: '', onboarding_steps: null }
    const { state } = await setupHost()

    expect(state.targetOptions.value).toHaveLength(2)
    expect(state.isKnownTarget('#logo')).toBe(true)
    expect(state.isKnownTarget('#unknown')).toBe(false)

    const labelVNode = state.renderTargetLabel({ label: 'L', value: '#v' } as any)
    const knownTag = state.renderTargetTag({ option: { value: '#logo' } } as any)
    const unknownTag = state.renderTargetTag({ option: { value: '#x' } } as any)
    expect(labelVNode.type).toBe('div')
    expect(knownTag.type).toBe('span')
    expect(unknownTag.type).toBe('span')
  })

  it('onSave handles success and error', async () => {
    settingsData.value = { onboarding_enabled: true, onboarding_reset_trigger: '', onboarding_steps: null }
    const { state } = await setupHost()

    api.mockResolvedValueOnce({ onboarding_enabled: false, onboarding_reset_trigger: 'r1' })
    await state.onSave()
    expect(api).toHaveBeenCalledWith('/admin/system/settings', {
      method: 'PATCH',
      body: { onboarding_enabled: true },
    })
    expect(invalidateQueries).toHaveBeenCalled()
    expect(setSettings).toHaveBeenCalled()
    expect(message.success).toHaveBeenCalledWith('admin.modules.saved')

    api.mockRejectedValueOnce(new Error('x'))
    await state.onSave()
    expect(message.error).toHaveBeenCalledWith('errors.generic')
  })

  it('onSaveSteps validates and handles success/error', async () => {
    settingsData.value = { onboarding_enabled: true, onboarding_reset_trigger: '', onboarding_steps: null }
    const { state } = await setupHost()

    state.stepsForm.value = [{ id: '', selector: '', title: '', body: '', is_new: false, _key: 'k' }]
    await state.onSaveSteps()
    expect(message.error).toHaveBeenCalledWith('admin.modules.onboarding.stepsValidationError')

    state.stepsForm.value = [{ id: 'a', selector: ' #logo ', title: ' T ', body: 'b', is_new: true, _key: 'k' }]
    api.mockResolvedValueOnce({
      onboarding_enabled: true,
      onboarding_reset_trigger: 'r2',
      onboarding_steps: [{ id: 'a', selector: '#logo', title: 'T', body: 'b', is_new: true }],
    })
    await state.onSaveSteps()
    expect(state.hasCustom.value).toBe(true)
    expect(message.success).toHaveBeenCalledWith('admin.modules.saved')

    api.mockRejectedValueOnce(new Error('x'))
    await state.onSaveSteps()
    expect(message.error).toHaveBeenCalledWith('errors.generic')
  })

  it('onResetStepViews handles no-id, success and error', async () => {
    settingsData.value = { onboarding_enabled: true, onboarding_reset_trigger: '', onboarding_steps: null }
    const { state } = await setupHost()

    await state.onResetStepViews({ id: '', selector: '', title: '', body: '', is_new: false })
    expect(message.error).toHaveBeenCalledWith('admin.modules.onboarding.stepResetViewsNoId')

    api.mockResolvedValueOnce({ updated: 3, step_id: 's1' })
    await state.onResetStepViews({ id: 's1', selector: '', title: '', body: '', is_new: false })
    expect(message.success).toHaveBeenCalledWith('admin.modules.onboarding.stepResetViewsSuccess:{"count":3}')
    expect(state.resettingStepId.value).toBe('')

    api.mockRejectedValueOnce(new Error('x'))
    await state.onResetStepViews({ id: 's2', selector: '', title: '', body: '', is_new: false })
    expect(message.error).toHaveBeenCalledWith('errors.generic')
  })

  it('onResetSteps and onReset handle success and error', async () => {
    settingsData.value = { onboarding_enabled: true, onboarding_reset_trigger: 'old', onboarding_steps: null }
    const { state } = await setupHost()

    api.mockResolvedValueOnce({ onboarding_enabled: true, onboarding_reset_trigger: 'n', onboarding_steps: null })
    await state.onResetSteps()
    expect(state.hasCustom.value).toBe(false)

    api.mockRejectedValueOnce(new Error('x'))
    await state.onResetSteps()
    expect(message.error).toHaveBeenCalledWith('errors.generic')

    api.mockResolvedValueOnce({ updated: 10, reset_trigger: '2026-02-01T00:00:00.000Z' })
    await state.onReset()
    expect(state.lastResetTrigger.value).toBe('2026-02-01T00:00:00.000Z')
    expect(message.success).toHaveBeenCalledWith('admin.modules.onboarding.resetSuccess:{"count":10}')

    api.mockRejectedValueOnce(new Error('x'))
    await state.onReset()
    expect(message.error).toHaveBeenCalledWith('errors.generic')
  })

  it('onDiscardSteps syncs back to current server state', async () => {
    settingsData.value = {
      onboarding_enabled: true,
      onboarding_reset_trigger: '',
      onboarding_steps: [{ id: 'z', selector: '#logo', title: 'Server', body: '', is_new: false }],
    }
    const { state } = await setupHost()
    state.stepsForm.value[0].title = 'Local'
    state.onDiscardSteps()
    expect(state.stepsForm.value[0].title).toBe('Server')
  })
})
