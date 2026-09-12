import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

const updateSignatureSettings = vi.fn()

const settingsData = ref<any>(undefined)
const modulesData = ref<any>({ signature: true })

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('naive-ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('naive-ui')>()
  return {
    ...actual,
    useMessage: () => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn() }),
  }
})

vi.mock('../../src/queries/admin', () => ({
  useModulesAdminQuery: () => ({ data: modulesData }),
}))

vi.mock('../../src/queries/signature', () => ({
  useSignatureSettingsQuery: () => ({ data: settingsData }),
  useUpdateSignatureSettingsMutation: () => ({
    mutateAsync: (...args: any[]) => updateSignatureSettings(...args),
  }),
}))

vi.mock('../../src/api/signature', () => ({
  updateSignatureSettings: (...args: any[]) => updateSignatureSettings(...args),
}))

import SignatureModuleSettings from '../../src/components/admin/SignatureModuleSettings.vue'

/** Настройки без опциональных коллекций (cities/office_phones) — генерированный
 *  тип делает их optional; watch обязан подставить пустые массивы, а не упасть. */
const SETTINGS_WITHOUT_OPTIONALS = {
  support_email: 'it@mage.ru',
  company_url: 'https://mage.ru',
  logo_base_url: 'https://mage.ru',
  attr_mobile: 'mobile',
  attr_office_phone: 'telephoneNumber',
  attr_city: 'city',
}

describe('SignatureModuleSettings', () => {
  beforeEach(() => {
    updateSignatureSettings.mockReset()
    updateSignatureSettings.mockResolvedValue(undefined)
    settingsData.value = undefined
    modulesData.value = { signature: true }
  })

  it('watch подставляет пустые массивы, когда cities/office_phones отсутствуют', async () => {
    settingsData.value = { ...SETTINGS_WITHOUT_OPTIONALS }
    const wrapper = mount(SignatureModuleSettings)
    await new Promise((r) => setTimeout(r, 0))

    const vm = wrapper.vm as any
    expect(vm.form.cities).toEqual([])
    expect(vm.form.office_phones).toEqual([])
    expect(vm.form.support_email).toBe('it@mage.ru')
  })

  it('save отправляет office_phones как массив (фильтр пустых)', async () => {
    settingsData.value = { ...SETTINGS_WITHOUT_OPTIONALS }
    const wrapper = mount(SignatureModuleSettings)
    await new Promise((r) => setTimeout(r, 0))

    await (wrapper.vm as any).onSave()

    expect(updateSignatureSettings).toHaveBeenCalledTimes(1)
    const payload = updateSignatureSettings.mock.calls[0][0]
    expect(payload.office_phones).toEqual([])
    expect(payload.support_email).toBe('it@mage.ru')
  })
})
