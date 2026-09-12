/**
 * Mount-smoke ModulesTab.vue: проверяет что таб действительно монтируется
 * с моками queries/api и отображает корневую разметку.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'text', 'loading', 'disabled', 'ghost'],
    emits: ['click'],
  },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'clearable', 'type', 'showPasswordOn'],
    emits: ['update:value'],
  },
  NForm: { template: '<form><slot /></form>', props: ['model', 'labelPlacement'] },
  NFormItem: { template: '<div class="n-form-item"><slot /></div>', props: ['label'] },
  NSwitch: {
    template: '<input type="checkbox" :checked="value" @change="$emit(\'update:value\', $event.target.checked)" />',
    props: ['value', 'loading'],
    emits: ['update:value'],
  },
  NDrawer: { template: '<div v-if="show"><slot /></div>', props: ['show', 'width', 'placement'] },
  NDrawerContent: { template: '<div><slot /></div>', props: ['title', 'closable'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('vue-router', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn() })),
}))

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
}))

vi.mock('../../src/api', () => ({
  api: vi.fn().mockResolvedValue({}),
}))

const modulesDataRef = ref<unknown>({
  nextcloud: { enabled: false },
  photos: { enabled: true, widget_limit: 8, max_size_mb: 50, allowed_mime: [], strip_gps: true },
  meetings: { enabled: true, calendar_start_hour: 8, calendar_end_hour: 20, max_recurrence_horizon_days: 365, min_search_chars: 2 },
})

const sysSettingsDataRef = ref<unknown>({
  nextcloud_url: 'https://nc.example',
  nc_service_username: 'svc',
  nc_files_root: 'PortalFiles',
  nc_user_id_field: 'email',
  nc_service_app_password_set: false,
  video_gallery_url: '',
  onboarding_enabled: true,
  onboarding_reset_trigger: '',
  onboarding_steps: null,
})

vi.mock('../../src/queries/admin', () => ({
  useModulesAdminQuery: vi.fn(() => ({ data: modulesDataRef, isError: ref(false) })),
  useSystemSettingsQuery: vi.fn(() => ({ data: sysSettingsDataRef, isError: ref(false) })),
}))

vi.mock('../../src/queries/keys', () => ({
  queryKeys: {
    admin: {
      modules: () => ['admin', 'modules'],
      systemSettings: () => ['admin', 'systemSettings'],
    },
  },
}))

vi.mock('../../src/router', () => ({
  ROUTES: { PHOTOS: '/photos', MEETINGS: '/meetings' },
}))

vi.mock('../../src/composables/useManageDrawer', () => ({
  useManageDrawer: () => ({
    open: vi.fn(),
    close: vi.fn(),
    is: vi.fn(() => false),
    current: ref(null),
  }),
}))

vi.mock('../../src/stores/onboarding', () => ({
  useOnboardingSettingsStore: () => ({
    setSettings: vi.fn(),
  }),
}))

describe('ModulesTab.vue (mount smoke)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('mounts and renders module sections', async () => {
    const { default: ModulesTab } = await import('../../src/pages/admin/tabs/ModulesTab.vue')
    const wrapper = mount(ModulesTab, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.findAll('.branding-section').length).toBeGreaterThanOrEqual(3)
  })

  it('renders modules-hint', async () => {
    const { default: ModulesTab } = await import('../../src/pages/admin/tabs/ModulesTab.vue')
    const wrapper = mount(ModulesTab, { global: { plugins: [i18n] } })
    expect(wrapper.find('.modules-hint').exists()).toBe(true)
  })

  it('renders module switches', async () => {
    const { default: ModulesTab } = await import('../../src/pages/admin/tabs/ModulesTab.vue')
    const wrapper = mount(ModulesTab, { global: { plugins: [i18n] } })
    await flushPromises()
    // Photos, meetings, nextcloud, onboarding switches → ≥3
    expect(wrapper.findAll('input[type="checkbox"]').length).toBeGreaterThanOrEqual(3)
  })
})
