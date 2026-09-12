/**
 * ApprovalsSettings.vue (admin): write-only пароль, dirty-tracking Save,
 * buildDto (пустой пароль не уходит), «Проверить подключение» (ok/fail).
 * Клон directum-settings.spec.ts.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'loading', 'disabled'],
    emits: ['click'],
  },
  NForm: { template: '<form><slot /></form>', props: ['labelPlacement', 'showFeedback'] },
  NFormItem: { template: '<div class="n-form-item"><slot /><slot name="feedback" /></div>', props: ['label'] },
  NInput: {
    template: '<input :value="value ?? \'\'" :placeholder="placeholder ?? \'\'" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type', 'showPasswordOn', 'inputProps'],
    emits: ['update:value'],
  },
  NSpin: { template: '<div><slot /></div>', props: ['show'] },
  useMessage: () => ({ success: vi.fn(), error: vi.fn() }),
}))

const mutateAsync = vi.fn().mockResolvedValue({})
const testConnection = vi.fn()

vi.mock('../../src/queries/approvals', () => ({
  useApprovalsSettingsQuery: () => ({
    data: ref({
      base_url: 'https://erp.mage.ru/MageErp/hs/Auth',
      auth_username: 'Portal',
      password_set: true,
      configured: true,
      updated_at: null,
    }),
    isLoading: ref(false),
  }),
  usePutApprovalsSettingsMutation: () => ({ mutateAsync, isPending: ref(false) }),
}))

vi.mock('../../src/api/approvals', () => ({
  testApprovalsConnection: (...args: unknown[]) => testConnection(...args),
}))

import ApprovalsSettings from '../../src/components/admin/ApprovalsSettings.vue'

async function mountSettings() {
  const w = mount(ApprovalsSettings, { global: { plugins: [i18n] } })
  await flushPromises()
  return w
}

describe('ApprovalsSettings.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mutateAsync.mockResolvedValue({})
    testConnection.mockReset()
  })

  it('гидрируется с серверных настроек, пароль не в форме', async () => {
    const w = await mountSettings()
    const inputs = w.findAll('input')
    const values = inputs.map((i) => i.element as HTMLInputElement).map((i) => i.value)
    expect(values).toContain('https://erp.mage.ru/MageErp/hs/Auth')
    expect(values).toContain('Portal')
    expect(values).not.toContain('secret')
    const save = w.findAll('.n-button').find((b) => b.text() !== '' && b.attributes('disabled') !== undefined)
    expect(save).toBeDefined() // dirty=false → Save задизейблен
  })

  it('buildDto: пустой пароль не уходит в PUT', async () => {
    const w = await mountSettings()
    const inputs = w.findAll('input')
    await inputs[3].setValue('') // пароль пуст
    const save = w.findAll('.n-button').find((b) => b.text() !== '' && b.attributes('disabled') === undefined)
    await save!.trigger('click')
    await flushPromises()
    expect(mutateAsync).toHaveBeenCalledTimes(1)
    const dto = mutateAsync.mock.calls[0][0] as Record<string, string>
    expect(dto.base_url).toBe('https://erp.mage.ru/MageErp/hs/Auth')
    expect(dto.auth_username).toBe('Portal')
    expect('auth_password' in dto).toBe(false)
  })

  it('успешное сохранение сбрасывает dirty', async () => {
    const w = await mountSettings()
    const inputs = w.findAll('input')
    await inputs[2].setValue('Portal2')
    const save = () => w.findAll('.n-button').find((b) => b.text() !== '' && b.attributes('disabled') === undefined)
    await save()!.trigger('click')
    await flushPromises()
    expect(mutateAsync).toHaveBeenCalled()
    expect(w.find('.approvals__save-result--ok').exists()).toBe(true)
  })

  it('ошибка сохранения — fail-фидбэк', async () => {
    mutateAsync.mockRejectedValue(new Error('boom'))
    const w = await mountSettings()
    const inputs = w.findAll('input')
    await inputs[2].setValue('Portal2')
    await w.findAll('.n-button').find((b) => b.text() !== '' && b.attributes('disabled') === undefined)!.trigger('click')
    await flushPromises()
    expect(w.find('.approvals__save-result--fail').exists()).toBe(true)
  })

  it('«Проверить подключение»: ok и fail', async () => {
    testConnection.mockResolvedValue({ ok: true, message: 'ERP доступна', latency_ms: 10 })
    const w = await mountSettings()
    const test = () => w.findAll('.n-button').find((b) => b.text().includes('testConnection'))
    await test()!.trigger('click')
    await flushPromises()
    expect(w.find('.approvals__save-result--ok').exists()).toBe(true)

    testConnection.mockResolvedValue({ ok: false, message: '401', latency_ms: 10 })
    await test()!.trigger('click')
    await flushPromises()
    expect(w.find('.approvals__save-result--fail').exists()).toBe(true)
  })
})
