/**
 * Smoke-тест OnboardingModuleSettings.vue: монтируется без ошибок при разных
 * состояниях admin-настроек (нет данных / default steps / custom override).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'loading', 'disabled', 'quaternary'],
    emits: ['click'],
  },
  NCheckbox: {
    template: '<input type="checkbox" />',
    props: ['checked'],
    emits: ['update:checked'],
  },
  NFormItem: { template: '<div class="n-form-item"><slot /></div>', props: ['label'] },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type'],
    emits: ['update:value'],
  },
  NPopconfirm: {
    template: '<div><slot name="trigger" /></div>',
    props: ['positiveText', 'negativeText'],
    emits: ['positive-click'],
  },
  NSelect: {
    template: '<select />',
    props: ['value', 'options', 'filterable', 'tag', 'placeholder', 'renderLabel', 'renderTag'],
    emits: ['update:value'],
  },
  NSwitch: { template: '<input type="checkbox" />', props: ['value'], emits: ['update:value'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

const settingsRef = ref<unknown>(null)

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({}),
}))

vi.mock('../../src/queries/admin', () => ({
  useSystemSettingsQuery: vi.fn(() => ({ data: settingsRef })),
}))

vi.mock('../../src/queries/keys', () => ({
  queryKeys: { admin: { systemSettings: () => ['admin', 'systemSettings'] } },
}))

vi.mock('../../src/stores/onboarding', () => ({
  defaultOnboardingSteps: () => [
    { id: 'welcome', selector: '#welcome', title: 'Welcome', body: '', is_new: false },
  ],
  useOnboardingSettingsStore: () => ({
    setSettings: vi.fn(),
  }),
}))

vi.mock('../../src/utils/tourTargets', () => ({
  getTourTargetOptions: () => [{ group: 'Main', label: 'Home', value: '#home' }],
  tourTargetLabelFor: (s: string) => (s === '#home' ? 'Home' : null),
}))

describe('OnboardingModuleSettings.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    settingsRef.value = null
  })

  it('mounts without server data', async () => {
    const { default: Cmp } = await import('../../src/components/admin/onboarding/OnboardingModuleSettings.vue')
    const wrapper = mount(Cmp, { global: { plugins: [i18n] } })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.onboarding-module-settings').exists()).toBe(true)
  })

  it('shows default-steps note when no custom override', async () => {
    settingsRef.value = {
      onboarding_enabled: true,
      onboarding_reset_trigger: '',
      onboarding_steps: null,
    }
    const { default: Cmp } = await import('../../src/components/admin/onboarding/OnboardingModuleSettings.vue')
    const wrapper = mount(Cmp, { global: { plugins: [i18n] } })
    expect(wrapper.find('.settings-section__meta').exists()).toBe(true)
  })

  it('renders custom steps from server', async () => {
    settingsRef.value = {
      onboarding_enabled: true,
      onboarding_reset_trigger: '',
      onboarding_steps: [
        { id: 's1', selector: '#a', title: 'A', body: '', is_new: false },
        { id: 's2', selector: '#b', title: 'B', body: '', is_new: true },
      ],
    }
    const { default: Cmp } = await import('../../src/components/admin/onboarding/OnboardingModuleSettings.vue')
    const wrapper = mount(Cmp, { global: { plugins: [i18n] } })
    expect(wrapper.findAll('.step-item').length).toBe(2)
  })
})
