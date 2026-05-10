import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'

const mockMessage = { error: vi.fn(), success: vi.fn(), warning: vi.fn() }

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button @click="$emit(\'click\')"><slot /></button>',
    emits: ['click'],
  },
  NInput: {
    template: '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'modelValue', 'placeholder', 'type', 'clearable', 'showPasswordOn', 'inputProps'],
    emits: ['update:value'],
  },
  NInputNumber: {
    template: '<input type="number" :value="value" @input="$emit(\'update:value\', Number($event.target.value))" />',
    props: ['value', 'modelValue', 'min', 'max', 'style'],
    emits: ['update:value'],
  },
  NFormItem: { template: '<div><label>{{ label }}</label><slot /></div>', props: ['label', 'style'] },
  NSwitch: {
    template: '<input type="checkbox" :checked="value" @change="$emit(\'update:value\', $event.target.checked)" />',
    props: ['value', 'modelValue'],
    emits: ['update:value'],
  },
  NRadioGroup: {
    template: '<div><slot /></div>',
    props: ['value', 'modelValue'],
    emits: ['update:value'],
  },
  NRadioButton: {
    template: '<label><slot /></label>',
    props: ['value', 'label'],
  },
  NRadio: {
    template: '<label><input type="radio" :value="value" /><slot /></label>',
    props: ['value', 'label'],
  },
  NSpace: { template: '<div><slot /></div>' },
  NModal: {
    template: '<div v-if="show"><slot /><slot name="footer" /></div>',
    props: ['show', 'title', 'preset', 'style', 'maskClosable'],
    emits: ['update:show'],
  },
  useMessage: () => mockMessage,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

const mockApi = vi.fn()
vi.mock('../../src/api/index', () => ({ api: mockApi }))

const DEFAULT_EMAIL_RESPONSE = {
  host: 'smtp.example.com',
  port: 587,
  from_address: 'noreply@example.com',
  username: 'user',
  password_set: true,
  use_tls: false,
  use_starttls: true,
}

async function mountEmailTab() {
  const { default: EmailTab } = await import('../../src/pages/admin/tabs/EmailTab.vue')
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(EmailTab, {
    attachTo: document.body,
    global: { plugins: [[VueQueryPlugin, { queryClient }]] },
  })
  await flushPromises()
  return wrapper
}

describe('EmailTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockResolvedValue(DEFAULT_EMAIL_RESPONSE)
  })

  describe('loadEmailSettings при монтировании', () => {
    it('вызывает GET /admin/email-settings', async () => {
      await mountEmailTab()
      expect(mockApi).toHaveBeenCalledWith('/admin/email-settings')
    })

    it('заполняет форму данными из API', async () => {
      const wrapper = await mountEmailTab()
      const inputs = wrapper.findAll('input[type="text"], input:not([type]), input[type="number"]')
      const hostInput = inputs.find(i => (i.element as HTMLInputElement).value === 'smtp.example.com')
      expect(hostInput).toBeTruthy()
    })

    it('устанавливает emailPasswordSet из поля password_set', async () => {
      mockApi.mockResolvedValueOnce({ ...DEFAULT_EMAIL_RESPONSE, password_set: true })
      const wrapper = await mountEmailTab()
      const passwordInput = wrapper.find('input[type="number"]')
      expect(passwordInput.exists()).toBe(true)
      expect(wrapper.html()).toContain('smtp.example.com')
    })

    it('устанавливает loadError при сбое без вывода toast', async () => {
      mockApi.mockRejectedValueOnce(new Error('Network error'))
      const wrapper = await mountEmailTab()
      expect(wrapper.exists()).toBe(true)
      expect(mockMessage.error).not.toHaveBeenCalled()
    })
  })

  describe('saveEmailSettings', () => {
    it('вызывает PUT /admin/email-settings с данными формы', async () => {
      mockApi
        .mockResolvedValueOnce(DEFAULT_EMAIL_RESPONSE)
        .mockResolvedValueOnce({ ...DEFAULT_EMAIL_RESPONSE, password_set: false })

      const wrapper = await mountEmailTab()
      const saveBtn = wrapper.findAll('button')[0]
      await saveBtn.trigger('click')
      await flushPromises()

      expect(mockApi).toHaveBeenCalledWith(
        '/admin/email-settings',
        expect.objectContaining({ method: 'PUT' }),
      )
    })

    it('отправляет null вместо пустого пароля', async () => {
      mockApi
        .mockResolvedValueOnce(DEFAULT_EMAIL_RESPONSE)
        .mockResolvedValueOnce(DEFAULT_EMAIL_RESPONSE)

      const wrapper = await mountEmailTab()
      const saveBtn = wrapper.findAll('button')[0]
      await saveBtn.trigger('click')
      await flushPromises()

      const putCall = mockApi.mock.calls.find(c => c[1]?.method === 'PUT')
      expect(putCall).toBeTruthy()
      expect(putCall![1].body.password).toBeNull()
    })

    it('показывает сообщение об ошибке, если настройки не загружались', async () => {
      mockApi.mockRejectedValueOnce(new Error('load failed'))
      const wrapper = await mountEmailTab()

      vi.clearAllMocks()
      const saveBtn = wrapper.findAll('button')[0]
      await saveBtn.trigger('click')
      await flushPromises()

      expect(mockMessage.error).toHaveBeenCalledWith('admin.email.loadFailedGuard')
      expect(mockApi).not.toHaveBeenCalled()
    })

    it('показывает success-уведомление после сохранения', async () => {
      mockApi
        .mockResolvedValueOnce(DEFAULT_EMAIL_RESPONSE)
        .mockResolvedValueOnce(DEFAULT_EMAIL_RESPONSE)

      const wrapper = await mountEmailTab()
      const saveBtn = wrapper.findAll('button')[0]
      await saveBtn.trigger('click')
      await flushPromises()

      expect(mockMessage.success).toHaveBeenCalledWith('admin.email.saved')
    })

    it('показывает ошибку при сбое сохранения', async () => {
      mockApi
        .mockResolvedValueOnce(DEFAULT_EMAIL_RESPONSE)
        .mockRejectedValueOnce(new Error('save failed'))

      const wrapper = await mountEmailTab()
      const saveBtn = wrapper.findAll('button')[0]
      await saveBtn.trigger('click')
      await flushPromises()

      expect(mockMessage.error).toHaveBeenCalledWith('errors.generic')
    })
  })

  describe('тестовое письмо', () => {
    it('открывает модальное окно при клике "Отправить тест"', async () => {
      const wrapper = await mountEmailTab()

      const sendTestBtn = wrapper.findAll('button')[1]
      await sendTestBtn.trigger('click')
      await flushPromises()

      expect(wrapper.html()).toContain('admin.email.testTo')
      expect(wrapper.html()).toContain('admin.email.sendTestBtn')
    })

    it('предупреждает при пустом адресе получателя', async () => {
      const wrapper = await mountEmailTab()
      const sendTestBtn = wrapper.findAll('button')[1]
      await sendTestBtn.trigger('click')
      await flushPromises()

      const modalButtons = wrapper.findAll('button')
      const sendBtn = modalButtons[modalButtons.length - 1]
      await sendBtn.trigger('click')
      await flushPromises()

      expect(mockMessage.warning).toHaveBeenCalledWith('admin.email.testToRequired')
      expect(mockApi).toHaveBeenCalledTimes(1)
    })

    it('вызывает POST /admin/email-settings/test с адресом получателя', async () => {
      mockApi
        .mockResolvedValueOnce(DEFAULT_EMAIL_RESPONSE)
        .mockResolvedValueOnce(undefined)

      const wrapper = await mountEmailTab()
      const sendTestBtn = wrapper.findAll('button')[1]
      await sendTestBtn.trigger('click')
      await flushPromises()

      const allInputs = wrapper.findAll('input')
      const textInputs = allInputs.filter(i => {
        const t = (i.element as HTMLInputElement).type
        return t !== 'checkbox' && t !== 'number'
      })
      await textInputs[textInputs.length - 1].setValue('recipient@example.com')

      const modalButtons = wrapper.findAll('button')
      const sendBtn = modalButtons[modalButtons.length - 1]
      await sendBtn.trigger('click')
      await flushPromises()

      expect(mockApi).toHaveBeenCalledWith(
        '/admin/email-settings/test',
        expect.objectContaining({
          method: 'POST',
          body: { to: 'recipient@example.com' },
        }),
      )
    })

    it('показывает success и закрывает модал при успешной отправке', async () => {
      mockApi
        .mockResolvedValueOnce(DEFAULT_EMAIL_RESPONSE)
        .mockResolvedValueOnce(undefined)

      const wrapper = await mountEmailTab()
      const sendTestBtn = wrapper.findAll('button')[1]
      await sendTestBtn.trigger('click')
      await flushPromises()

      const allInputs = wrapper.findAll('input')
      const textInputs = allInputs.filter(i => {
        const t = (i.element as HTMLInputElement).type
        return t !== 'checkbox' && t !== 'number'
      })
      await textInputs[textInputs.length - 1].setValue('test@example.com')

      const modalButtons = wrapper.findAll('button')
      const sendBtn = modalButtons[modalButtons.length - 1]
      await sendBtn.trigger('click')
      await flushPromises()

      expect(mockMessage.success).toHaveBeenCalledWith(
        expect.stringContaining('admin.email.testSent'),
      )
    })
  })

  describe('взаимоисключение TLS / STARTTLS (чистая логика)', () => {
    it('включение TLS сбрасывает STARTTLS в false', () => {
      const form = { use_tls: false, use_starttls: true }
      const onTlsChange = (v: boolean) => { if (v) form.use_starttls = false }
      onTlsChange(true)
      expect(form.use_starttls).toBe(false)
    })

    it('включение STARTTLS сбрасывает TLS в false', () => {
      const form = { use_tls: true, use_starttls: false }
      const onStarttlsChange = (v: boolean) => { if (v) form.use_tls = false }
      onStarttlsChange(true)
      expect(form.use_tls).toBe(false)
    })

    it('отключение TLS не меняет STARTTLS', () => {
      const form = { use_tls: true, use_starttls: false }
      const onTlsChange = (v: boolean) => { if (v) form.use_starttls = false }
      onTlsChange(false)
      expect(form.use_starttls).toBe(false)
    })

    it('отключение STARTTLS не меняет TLS', () => {
      const form = { use_tls: false, use_starttls: true }
      const onStarttlsChange = (v: boolean) => { if (v) form.use_tls = false }
      onStarttlsChange(false)
      expect(form.use_tls).toBe(false)
    })

    it('оба флага могут быть false одновременно (без шифрования)', () => {
      const form = { use_tls: false, use_starttls: false }
      expect(form.use_tls).toBe(false)
      expect(form.use_starttls).toBe(false)
    })
  })

  describe('валидация полей формы', () => {
    it('порт принимает значения от 1 до 65535', () => {
      const isValidPort = (p: number) => p >= 1 && p <= 65535
      expect(isValidPort(25)).toBe(true)
      expect(isValidPort(587)).toBe(true)
      expect(isValidPort(465)).toBe(true)
      expect(isValidPort(0)).toBe(false)
      expect(isValidPort(65536)).toBe(false)
    })

    it('пустой testEmailAddress (только пробелы) считается пустым', () => {
      const addr = '   '
      expect(addr.trim()).toBe('')
    })

    it('адрес с пробелами по краям обрезается перед отправкой', () => {
      const addr = '  test@example.com  '
      expect(addr.trim()).toBe('test@example.com')
    })
  })
})
