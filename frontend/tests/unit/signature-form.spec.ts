import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

const generateSignature = vi.fn()

const configData = ref<any>(undefined)
const modulesStore = { isEnabled: vi.fn(() => true) }

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('../../src/stores/modules', () => ({
  useModulesStore: () => modulesStore,
}))

vi.mock('../../src/queries/signature', () => ({
  useSignatureConfigQuery: () => ({
    data: configData,
    isLoading: ref(false),
    isError: ref(false),
  }),
}))

vi.mock('../../src/api/signature', () => ({
  generateSignature: (...args: any[]) => generateSignature(...args),
}))

const EMPTY_PREFILL = {
  name: '',
  surname: '',
  position: '',
  language: 'Ru',
  email: '',
  mobile_phone: '',
  office_phone: null,
  extension: null,
  city_id: null,
}

function config(prefill: Record<string, any> = {}) {
  return {
    cities: [
      { id: 1, label_ru: 'Мурманск', label_eng: 'Murmansk', suffix_ru: '', suffix_eng: '' },
      { id: 2, label_ru: 'Москва', label_eng: 'Moscow', suffix_ru: ', МАГЭ', suffix_eng: ', MAGE' },
    ],
    office_phones: ['+7 (8152) 400 580', '+7 (495) 66 555 66'],
    support_email: 'it@mage.ru',
    email_domain: 'mage.ru',
    prefill: { ...EMPTY_PREFILL, ...prefill },
  }
}

async function setup() {
  let api: any = null
  const mod = await import('../../src/pages/composables/useSignatureForm')
  const Host = defineComponent({
    setup() {
      api = mod.useSignatureForm()
      return () => h('div')
    },
  })
  const wrapper = mount(Host)
  await nextTick()
  return { api, wrapper }
}

describe('useSignatureForm', () => {
  beforeEach(() => {
    generateSignature.mockReset()
    configData.value = config()
  })

  it('defaults city from config; office phone empty without a match', async () => {
    const { api } = await setup()
    expect(api.form.cityId).toBe(1)
    expect(api.form.officePhone).toBeNull()
  })

  it('prefills from server-computed config.prefill (mobile masked)', async () => {
    configData.value = config({
      name: 'Михаил',
      surname: 'Гаврин',
      position: 'Инженер',
      email: 'ivan@mage.ru',
      language: 'Eng',
      mobile_phone: '89001234567',
      office_phone: '+7 (495) 66 555 66',
      extension: '346',
      city_id: 2,
    })
    const { api } = await setup()
    expect(api.form.name).toBe('Михаил')
    expect(api.form.surname).toBe('Гаврин')
    expect(api.form.position).toBe('Инженер')
    expect(api.form.email).toBe('ivan@mage.ru')
    expect(api.form.language).toBe('Eng')
    expect(api.form.mobilePhone).toBe('+7 (900) 123 4567')
    expect(api.form.officePhone).toBe('+7 (495) 66 555 66')
    expect(api.form.extension).toBe('346')
    expect(api.form.cityId).toBe(2)
  })

  it('isValid reflects required fields and email domain', async () => {
    const { api } = await setup()
    expect(api.isValid.value).toBe(false)

    api.form.name = 'Иван'
    api.form.surname = 'Петров'
    api.form.position = 'Инженер'
    api.form.email = 'ivan@mage.ru'
    await nextTick()
    expect(api.isValid.value).toBe(true)

    api.form.email = 'ivan@gmail.com'
    await nextTick()
    expect(api.isValid.value).toBe(false)
  })

  it('isValid false for bad extension', async () => {
    const { api } = await setup()
    api.form.name = 'Иван'
    api.form.surname = 'Петров'
    api.form.position = 'Инженер'
    api.form.email = 'ivan@mage.ru'
    api.form.extension = '12'
    await nextTick()
    expect(api.isValid.value).toBe(false)
  })

  it('onExtensionInput keeps only digits, max 3', async () => {
    const { api } = await setup()
    api.onExtensionInput('a1b2c3d4')
    expect(api.form.extension).toBe('123')
  })

  it('onMobileInput applies phone mask', async () => {
    const { api } = await setup()
    api.onMobileInput('89001234567')
    expect(api.form.mobilePhone).toBe('+7 (900) 123 4567')
  })

  it('generate sends trimmed request and stores result', async () => {
    generateSignature.mockResolvedValue({ html: '<b>sig</b>', filename: 'ИванПетров_Ru.htm' })
    const { api } = await setup()
    api.form.name = '  Иван  '
    api.form.surname = 'Петров'
    api.form.position = 'Инженер'
    api.form.email = 'ivan@mage.ru'
    await nextTick()

    await api.generate()

    expect(generateSignature).toHaveBeenCalledTimes(1)
    const sent = generateSignature.mock.calls[0][0]
    expect(sent.name).toBe('Иван')
    expect(sent.city_id).toBe(1)
    expect(sent.email).toBe('ivan@mage.ru')
    expect(api.previewHtml.value).toBe('<b>sig</b>')
    expect(api.filename.value).toBe('ИванПетров_Ru.htm')
    expect(api.generated.value).toBe(true)
  })

  it('generate skips request when form invalid', async () => {
    const { api } = await setup()
    await api.generate()
    expect(generateSignature).not.toHaveBeenCalled()
    expect(api.generateError.value).toBeTruthy()
  })

  it('mailtoSupport derives from support email', async () => {
    const { api } = await setup()
    expect(api.mailtoSupport.value).toBe('mailto:it@mage.ru')
    expect(api.emailDomain.value).toBe('mage.ru')
  })
})
