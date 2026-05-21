import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api'
import { i18n } from '../i18n'

export interface OnboardingStep {
  id: string
  selector: string
  title: string
  body: string
  is_new?: boolean
}

export interface OnboardingPublicSettings {
  onboarding_enabled: boolean
  onboarding_reset_trigger: string
  onboarding_steps: OnboardingStep[] | null
}

const DEFAULTS: OnboardingPublicSettings = {
  onboarding_enabled: true,
  onboarding_reset_trigger: '',
  onboarding_steps: null,
}

export function defaultOnboardingSteps(): OnboardingStep[] {
  const t = i18n.global.t
  return [
    {
      id: 'default-news',
      selector: '.n-menu-item:has([data-tour-id="news"])',
      title: t('onboarding.steps.news.title'),
      body: t('onboarding.steps.news.body'),
      is_new: false,
    },
    {
      id: 'default-kb',
      selector: '.n-menu-item:has([data-tour-id="kb"])',
      title: t('onboarding.steps.kb.title'),
      body: t('onboarding.steps.kb.body'),
      is_new: false,
    },
    {
      id: 'default-links',
      selector: '.n-menu-item:has([data-tour-id="links"])',
      title: t('onboarding.steps.links.title'),
      body: t('onboarding.steps.links.body'),
      is_new: false,
    },
    {
      id: 'default-profile',
      selector: '.app-header .user-pill',
      title: t('onboarding.steps.profile.title'),
      body: t('onboarding.steps.profile.body'),
      is_new: false,
    },
  ]
}

export const useOnboardingSettingsStore = defineStore('onboardingSettings', () => {
  const settings = ref<OnboardingPublicSettings>({ ...DEFAULTS })
  const loaded = ref(false)

  const onboardingEnabled = computed(() => settings.value.onboarding_enabled)
  const onboardingResetTrigger = computed(() => settings.value.onboarding_reset_trigger)
  const onboardingSteps = computed<OnboardingStep[]>(() => {
    const override = settings.value.onboarding_steps
    if (override && override.length > 0) return override
    return defaultOnboardingSteps()
  })
  const hasCustomSteps = computed(() => {
    const v = settings.value.onboarding_steps
    return Array.isArray(v) && v.length > 0
  })

  async function load() {
    try {
      const data = await api<OnboardingPublicSettings>('/portal/onboarding')
      settings.value = { ...DEFAULTS, ...data }
    } catch (err) {
      console.error('[onboarding] Failed to load settings:', err)
    }
    loaded.value = true
  }

  function setSettings(data: Partial<OnboardingPublicSettings>): void {
    settings.value = { ...DEFAULTS, ...settings.value, ...data }
    loaded.value = true
  }

  return {
    settings,
    loaded,
    onboardingEnabled,
    onboardingResetTrigger,
    onboardingSteps,
    hasCustomSteps,
    load,
    setSettings,
  }
})
