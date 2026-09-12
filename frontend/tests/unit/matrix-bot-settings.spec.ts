/**
 * Unit-тесты компонента MatrixBotSettings (админка → Корпоративный чат).
 *
 * Токен write-only (не предзаполняется, пусто = не менять), dirty-трекинг,
 * валидация включения без токена/обязательных полей, тест-кнопка.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { MatrixBotTestResult } from '../../src/api/matrixBot'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const messageMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}))

vi.mock('naive-ui', () => ({
  NForm: { template: '<form><slot /></form>' },
  NFormItem: { template: '<div class="n-form-item"><label><slot name="label" /></label><slot /></div>' },
  NInput: {
    template: '<input class="n-input" :value="value" :type="type" :placeholder="placeholder" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'type', 'placeholder', 'inputProps'],
    emits: ['update:value'],
  },
  NCheckbox: {
    template: '<label class="n-checkbox"><input type="checkbox" :checked="checked" @change="$emit(\'update:checked\', $event.target.checked)" /><slot /></label>',
    props: ['checked'],
    emits: ['update:checked'],
  },
  NButton: { template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>', props: ['size', 'type', 'disabled', 'loading'], emits: ['click'] },
  NSpin: { template: '<div class="n-spin"><slot /></div>', props: ['show'] },
  useMessage: () => messageMock,
}))

const matrixApiMock = vi.hoisted(() => ({
  fetchMatrixBot: vi.fn(async () => ({})),
  putMatrixBot: vi.fn(async () => ({})),
  testMatrixBot: vi.fn(async (): Promise<MatrixBotTestResult> => ({ ok: true })),
}))

vi.mock('../../src/api/matrixBot', () => matrixApiMock)

const queryMocks = vi.hoisted(() => ({
  useMatrixBotQuery: vi.fn(),
  usePutMatrixBotMutation: vi.fn(),
}))

vi.mock('../../src/queries/admin', () => queryMocks)
vi.mock('../../src/utils/parseApiError', () => ({ parseApiError: () => 'Ошибка' }))

import MatrixBotSettings from '../../src/components/admin/MatrixBotSettings.vue'

function makeSettingsOut(overrides: Record<string, unknown> = {}) {
  return {
    configured: true,
    enabled: false,
    access_token_set: true,
    homeserver_url: 'https://matrix.mage.ru',
    server_name: 'matrix.mage.ru',
    bot_user_id: '@portal-bot:matrix.mage.ru',
    updated_at: '2026-08-16T00:00:00Z',
    ...overrides,
  }
}

function mountComponent(data: Record<string, unknown>) {
  const mutateAsync = vi.fn(async () => ({}))
  queryMocks.useMatrixBotQuery.mockReturnValue({
    data: ref(data),
    isLoading: ref(false),
  })
  queryMocks.usePutMatrixBotMutation.mockReturnValue({
    mutateAsync,
    isPending: ref(false),
  })
  const wrapper = mount(MatrixBotSettings, { global: { plugins: [i18n] } })
  return { wrapper, mutateAsync }
}

describe('MatrixBotSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('форма заполняется из GET; токен никогда не предзаполняется', async () => {
    const { wrapper } = mountComponent(makeSettingsOut())
    await flushPromises()
    const inputs = wrapper.findAll('.n-input')
    expect((inputs[0].element as HTMLInputElement).value).toBe('') // токен write-only
    expect((inputs[1].element as HTMLInputElement).value).toBe('https://matrix.mage.ru')
    expect((inputs[2].element as HTMLInputElement).value).toBe('matrix.mage.ru')
    expect((inputs[3].element as HTMLInputElement).value).toBe('@portal-bot:matrix.mage.ru')
  })

  it('Save без нового токена не передаёт access_token (прежний шифр остаётся)', async () => {
    const { wrapper, mutateAsync } = mountComponent(makeSettingsOut())
    await flushPromises()
    await wrapper.find('.n-checkbox input').setValue(true)
    await wrapper.findAll('.n-button')[0].trigger('click')
    await flushPromises()

    expect(mutateAsync).toHaveBeenCalledWith(
      expect.not.objectContaining({ access_token: expect.anything() }),
    )
    expect(messageMock.success).toHaveBeenCalled()
  })

  it('Save с введённым токеном передаёт его', async () => {
    const { wrapper, mutateAsync } = mountComponent(makeSettingsOut())
    await flushPromises()
    await wrapper.findAll('.n-input')[0].setValue('mct_new')
    await wrapper.find('.n-checkbox input').setValue(true)
    await wrapper.findAll('.n-button')[0].trigger('click')
    await flushPromises()

    expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ access_token: 'mct_new' }))
  })

  it('включение без сохранённого токена → ошибка, PUT не вызывается', async () => {
    const { wrapper, mutateAsync } = mountComponent(makeSettingsOut({ access_token_set: false }))
    await flushPromises()
    await wrapper.find('.n-checkbox input').setValue(true)
    await wrapper.findAll('.n-button')[0].trigger('click')
    await flushPromises()

    expect(messageMock.error).toHaveBeenCalled()
    expect(mutateAsync).not.toHaveBeenCalled()
  })

  it('включение без homeserver/bot_user_id → ошибка', async () => {
    const { wrapper, mutateAsync } = mountComponent(
      makeSettingsOut({ homeserver_url: null, bot_user_id: null }),
    )
    await flushPromises()
    await wrapper.find('.n-checkbox input').setValue(true)
    await wrapper.findAll('.n-button')[0].trigger('click')
    await flushPromises()

    expect(messageMock.error).toHaveBeenCalled()
    expect(mutateAsync).not.toHaveBeenCalled()
  })

  it('тест-кнопка показывает результат', async () => {
    matrixApiMock.testMatrixBot.mockResolvedValueOnce({ ok: true, detail: 'queued (delivery within ~30s)' })
    const { wrapper } = mountComponent(makeSettingsOut())
    await flushPromises()
    await wrapper.findAll('.n-button')[1].trigger('click')
    await flushPromises()

    expect(matrixApiMock.testMatrixBot).toHaveBeenCalledWith(null)
    expect(wrapper.text()).toContain('queued')
  })

  it('статус-баннер: поля заполнены + выключено → «настроено, но выключено»', async () => {
    const { wrapper } = mountComponent(makeSettingsOut({ enabled: false }))
    await flushPromises()
    expect(wrapper.find('.matrix-bot__status--off').exists()).toBe(true)
    expect(wrapper.find('.matrix-bot__status--on').exists()).toBe(false)
    expect(wrapper.find('.matrix-bot__notconfigured').exists()).toBe(false)
  })

  it('статус-баннер: включено → зелёный «настроено и включено»', async () => {
    const { wrapper } = mountComponent(makeSettingsOut({ enabled: true }))
    await flushPromises()
    expect(wrapper.find('.matrix-bot__status--on').exists()).toBe(true)
  })

  it('статус-баннер: нет токена → «не настроено»', async () => {
    const { wrapper } = mountComponent(makeSettingsOut({ access_token_set: false }))
    await flushPromises()
    expect(wrapper.find('.matrix-bot__notconfigured').exists()).toBe(true)
  })

  it('тест с указанным получателем: цель передаётся в API', async () => {
    matrixApiMock.testMatrixBot.mockResolvedValueOnce({ ok: true, detail: 'ok' })
    const { wrapper } = mountComponent(makeSettingsOut())
    await flushPromises()
    // Поле цели — четвёртый input (после токена/homeserver/server_name/bot_user_id).
    const targetInput = wrapper.findAll('.n-input')[4]
    await targetInput.setValue('@borzihin.vs:matrix.mage.ru')
    await wrapper.findAll('.n-button')[1].trigger('click')
    await flushPromises()

    expect(matrixApiMock.testMatrixBot).toHaveBeenCalledWith('@borzihin.vs:matrix.mage.ru')
  })

  it('тест с целью-логином: пробелы обрезаются, пусто → null', async () => {
    matrixApiMock.testMatrixBot.mockResolvedValueOnce({ ok: true })
    const { wrapper } = mountComponent(makeSettingsOut())
    await flushPromises()
    const targetInput = wrapper.findAll('.n-input')[4]
    await targetInput.setValue('   ')
    await wrapper.findAll('.n-button')[1].trigger('click')
    await flushPromises()

    expect(matrixApiMock.testMatrixBot).toHaveBeenCalledWith(null)
  })
})
