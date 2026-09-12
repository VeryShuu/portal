/**
 * DirectumSettings.vue: форма настроек вкладки Directum.
 *
 * Проверяется: рендер секций (общие + «Просроченные задачи»), write-only
 * пароль (placeholder «задан»), dirty-tracking кнопки Save, buildDto
 * (пароль не уходит пустым, notify_emails из comma-строки), локальная
 * валидация «включение требует кредов», кнопка «Проверить подключение».
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'loading', 'disabled'],
    emits: ['click'],
  },
  NInput: {
    template: '<input :value="value ?? \'\'" :placeholder="placeholder ?? \'\'" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'type', 'showPasswordOn', 'inputProps'],
    emits: ['update:value'],
  },
  NInputNumber: {
    template: '<input type="number" :value="value ?? \'\'" @input="$emit(\'update:value\', Number($event.target.value))" />',
    props: ['value', 'min', 'max', 'step'],
    emits: ['update:value'],
  },
  NForm: { template: '<form><slot /></form>', props: ['labelPlacement', 'showFeedback'] },
  NFormItem: { template: '<div class="n-form-item"><slot /><slot name="feedback" /></div>', props: ['label'] },
  NSpin: { template: '<div><slot /></div>', props: ['show'] },
  NSelect: {
    template: '<div class="n-select" />',
    props: ['value', 'options', 'multiple', 'clearable', 'placeholder'],
    emits: ['update:value'],
  },
  NSwitch: {
    template: '<input type="checkbox" class="n-switch" :checked="value" @change="$emit(\'update:value\', $event.target.checked)" />',
    props: ['value'],
    emits: ['update:value'],
  },
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

const mutateAsync = vi.fn().mockResolvedValue({})
const testConnection = vi.fn()

vi.mock('../../src/queries/directum', () => ({
  useDirectumSettingsQuery: () => ({
    data: ref({
      enabled: true,
      base_url: 'https://sed.mage.ru/Integration/odata',
      auth_username: 'PDC1\\svc',
      password_set: true,
      configured: true,
      overdue_run_hours: [10, 12],
      expected_interval_days: 2,
      notify_emails: ['a@mage.ru', 'b@mage.ru'],
      overdue_enabled: true,
      updated_at: null,
    }),
    isLoading: ref(false),
  }),
  usePutDirectumSettingsMutation: () => ({
    mutateAsync,
    isPending: ref(false),
  }),
}))

vi.mock('../../src/api/directum', () => ({
  testDirectumConnection: (...args: unknown[]) => testConnection(...args),
}))

import DirectumSettings from '../../src/components/admin/DirectumSettings.vue'

async function mountSettings() {
  const wrapper = mount(DirectumSettings, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('DirectumSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mutateAsync.mockClear().mockResolvedValue({})
    testConnection.mockClear()
  })

  it('рендерит секции и подставляет notify_emails из comma-строки', async () => {
    const wrapper = await mountSettings()
    // 4 NInput: base_url, username, password, notify_emails + 2 number.
    const textInputs = wrapper.findAll('input:not([type=number]):not([type=checkbox])')
    expect(textInputs.length).toBeGreaterThanOrEqual(4)
    expect((textInputs[3].element as HTMLInputElement).value).toBe('a@mage.ru, b@mage.ru')
    // Пароль write-only: placeholder «задан — введите новый».
    expect((textInputs[2].element as HTMLInputElement).placeholder).toContain('passwordKeep')
    // Обе секции отрисованы.
    expect(wrapper.findAll('.directum__subtitle').length).toBe(2)
  })

  it('Save заблокирован до изменений и активируется после правки', async () => {
    const wrapper = await mountSettings()
    const [saveBtn] = wrapper.findAll('button')
    expect((saveBtn.element as HTMLButtonElement).disabled).toBe(true)
    const username = wrapper.findAll('input:not([type=number]):not([type=checkbox])')[1]
    await username.setValue('PDC1\\svc2')
    expect((saveBtn.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('buildDto: пустой пароль не уходит, notify_emails парсится', async () => {
    const wrapper = await mountSettings()
    const notify = wrapper.findAll('input:not([type=number]):not([type=checkbox])')[3]
    await notify.setValue(' x@mage.ru , y@mage.ru ')
    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()
    expect(mutateAsync).toHaveBeenCalledTimes(1)
    const dto = mutateAsync.mock.calls[0][0]
    expect(dto.auth_password).toBeUndefined()
    expect(dto.notify_emails).toEqual(['x@mage.ru', 'y@mage.ru'])
    expect(dto.base_url).toBe('https://sed.mage.ru/Integration/odata')
  })

  it('новый пароль уходит в DTO', async () => {
    const wrapper = await mountSettings()
    const password = wrapper.findAll('input:not([type=number]):not([type=checkbox])')[2]
    await password.setValue('new-secret')
    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()
    expect(mutateAsync.mock.calls[0][0].auth_password).toBe('new-secret')
  })

  it('включение без кредов блокируется локально', async () => {
    const wrapper = await mountSettings()
    const username = wrapper.findAll('input:not([type=number]):not([type=checkbox])')[1]
    await username.setValue('')
    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()
    expect(mutateAsync).not.toHaveBeenCalled()
    expect(wrapper.find('.directum__save-result--fail').exists()).toBe(true)
  })

  it('«Проверить подключение»: успех и провал', async () => {
    testConnection.mockResolvedValueOnce({ ok: true, detail: 'ок' })
    const wrapper = await mountSettings()
    await wrapper.findAll('button')[1].trigger('click')
    await flushPromises()
    expect(wrapper.find('.directum__save-result--ok').text()).toContain('ок')

    testConnection.mockResolvedValueOnce({ ok: false, error: 'HTTP 401' })
    await wrapper.findAll('button')[1].trigger('click')
    await flushPromises()
    expect(wrapper.find('.directum__save-result--fail').text()).toContain('HTTP 401')
  })
})

describe('DirectumSettings: ошибочные ветки', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mutateAsync.mockClear()
    testConnection.mockClear()
  })

  it('ошибка сохранения — красный фидбэк', async () => {
    mutateAsync.mockRejectedValueOnce({ data: { detail: 'backend says no' } })
    const wrapper = await mountSettings()
    const notify = wrapper.findAll('input:not([type=number]):not([type=checkbox])')[3]
    await notify.setValue('a@mage.ru')
    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()
    const fail = wrapper.find('.directum__save-result--fail')
    expect(fail.exists()).toBe(true)
  })

  it('исключение при проверке подключения — красный фидбэк', async () => {
    testConnection.mockRejectedValueOnce({ message: 'network down' })
    const wrapper = await mountSettings()
    await wrapper.findAll('button')[1].trigger('click')
    await flushPromises()
    expect(wrapper.find('.directum__save-result--fail').exists()).toBe(true)
  })
})

describe('DirectumSettings: расписание (часы запуска)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mutateAsync.mockClear()
    testConnection.mockClear()
  })

  it('часы уходят в DTO отсортированными', async () => {
    const wrapper = await mountSettings()
    const { NSelect } = await import('naive-ui')
    wrapper.findComponent(NSelect).vm.$emit('update:value', [14, 10, 12])
    await flushPromises()
    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()
    expect(mutateAsync.mock.calls[0][0].overdue_run_hours).toEqual([10, 12, 14])
  })

  it('включённая задача без часов блокируется локально', async () => {
    const wrapper = await mountSettings()
    const { NSelect } = await import('naive-ui')
    wrapper.findComponent(NSelect).vm.$emit('update:value', [])
    await flushPromises()
    await wrapper.findAll('button')[0].trigger('click')
    await flushPromises()
    expect(mutateAsync).not.toHaveBeenCalled()
    expect(wrapper.find('.directum__save-result--fail').exists()).toBe(true)
  })
})
