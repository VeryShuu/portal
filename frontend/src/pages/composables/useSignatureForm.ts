import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  generateSignature,
  type SignatureConfig,
  type SignatureDevice,
  type SignatureGenerateRequest,
  type SignatureLanguage,
} from '../../api/signature'
import { useSignatureConfigQuery } from '../../queries/signature'
import { useModulesStore } from '../../stores/modules'

export interface SignatureFormState {
  name: string
  surname: string
  position: string
  language: SignatureLanguage
  device: SignatureDevice
  cityId: number | null
  officePhone: string | null
  extension: string
  mobilePhone: string
  email: string
}

const DEVICES: SignatureDevice[] = ['PC', 'Web', 'Apple', 'Phone']

/**
 * Phone mask ``+7 (XXX) XXX XXXX`` ported from ``./sign/web/js/Mob.js``.
 * Keeps only digits, normalises the leading country code to ``7`` and
 * progressively formats up to 11 digits.
 */
export function formatRuPhone(raw: string): string {
  let digits = raw.replace(/\D/g, '')
  if (digits.length === 0) return ''
  if (digits[0] === '8') digits = '7' + digits.slice(1)
  if (digits[0] !== '7') digits = '7' + digits
  digits = digits.slice(0, 11)

  const rest = digits.slice(1)
  let out = '+7'
  if (rest.length > 0) out += ' (' + rest.slice(0, 3)
  if (rest.length >= 3) out += ')'
  if (rest.length > 3) out += ' ' + rest.slice(3, 6)
  if (rest.length > 6) out += ' ' + rest.slice(6, 10)
  return out
}

export function useSignatureForm() {
  const { t } = useI18n()
  const modulesStore = useModulesStore()

  const moduleEnabled = computed(() => modulesStore.isEnabled('signature'))

  const configQuery = useSignatureConfigQuery({ enabled: moduleEnabled })
  const config = computed<SignatureConfig | undefined>(() => configQuery.data.value)

  const form = reactive<SignatureFormState>({
    name: '',
    surname: '',
    position: '',
    language: 'Ru',
    device: 'PC',
    cityId: null,
    officePhone: null,
    extension: '',
    mobilePhone: '',
    email: '',
  })

  const previewHtml = ref('')
  const filename = ref('')
  const generating = ref(false)
  const generated = ref(false)
  const generateError = ref<string | null>(null)

  const cityOptions = computed(() =>
    (config.value?.cities ?? []).map((c) => ({
      label: form.language === 'Ru' ? c.label_ru : c.label_eng,
      value: c.id,
    })),
  )

  const officePhoneOptions = computed(() =>
    (config.value?.office_phones ?? []).map((p) => ({ label: p, value: p })),
  )

  const languageOptions = computed(() => [
    { label: t('signature.lang.ru'), value: 'Ru' as SignatureLanguage },
    { label: t('signature.lang.eng'), value: 'Eng' as SignatureLanguage },
  ])

  const deviceOptions = computed(() =>
    DEVICES.map((d) => ({ label: t(`signature.device.${d}`), value: d })),
  )

  const supportEmail = computed(() => config.value?.support_email ?? '')
  const emailDomain = computed(() => config.value?.email_domain ?? 'mage.ru')

  // ── Prefill from profile, computed server-side and delivered via config. ────
  // All fields stay editable. Office phone is left empty when the profile value
  // does not match a configured number (the office select is strict).
  let prefilled = false
  watch(config, (cfg) => {
    if (!cfg || prefilled) return
    prefilled = true
    const p = cfg.prefill
    if (p) {
      if (p.name) form.name = p.name
      if (p.surname) form.surname = p.surname
      if (p.position) form.position = p.position
      if (p.email) form.email = p.email
      if (p.language) form.language = p.language
      if (p.mobile_phone) form.mobilePhone = formatRuPhone(p.mobile_phone)
      if (p.extension) form.extension = p.extension
      form.cityId = p.city_id ?? (cfg.cities.length > 0 ? cfg.cities[0].id : null)
      form.officePhone = p.office_phone ?? null
    } else {
      form.cityId = cfg.cities.length > 0 ? cfg.cities[0].id : null
      form.officePhone = null
    }
  }, { immediate: true })

  // Language switch re-validates the selected city against the localized list
  // (ids are stable across languages, so nothing to reset — labels recompute).

  const isValid = computed(() => {
    if (!form.name.trim() || form.name.trim().length > 20) return false
    if (!form.surname.trim() || form.surname.trim().length > 20) return false
    if (!form.position.trim() || form.position.trim().length > 150) return false
    if (form.cityId == null) return false
    if (form.extension && !/^[0-9]{3}$/.test(form.extension)) return false
    const email = form.email.trim().toLowerCase()
    if (!email.endsWith('@' + emailDomain.value)) return false
    return true
  })

  function buildRequest(): SignatureGenerateRequest {
    return {
      name: form.name.trim(),
      surname: form.surname.trim(),
      position: form.position.trim(),
      language: form.language,
      device: form.device,
      city_id: form.cityId as number,
      office_phone: form.officePhone || null,
      extension: form.extension || null,
      mobile_phone: form.mobilePhone.trim() || null,
      email: form.email.trim(),
    }
  }

  async function generate(): Promise<void> {
    if (!isValid.value) {
      generateError.value = t('signature.errors.invalidForm')
      return
    }
    generating.value = true
    generateError.value = null
    try {
      const res = await generateSignature(buildRequest())
      previewHtml.value = res.html
      filename.value = res.filename
      generated.value = true
    } catch {
      generateError.value = t('errors.generic')
    } finally {
      generating.value = false
    }
  }

  function onMobileInput(value: string): void {
    form.mobilePhone = formatRuPhone(value)
  }

  function onExtensionInput(value: string): void {
    form.extension = value.replace(/\D/g, '').slice(0, 3)
  }

  async function copyHtml(): Promise<boolean> {
    if (!previewHtml.value) return false
    try {
      if (navigator.clipboard && window.ClipboardItem) {
        const item = new ClipboardItem({
          'text/html': new Blob([previewHtml.value], { type: 'text/html' }),
          'text/plain': new Blob([previewHtml.value], { type: 'text/plain' }),
        })
        await navigator.clipboard.write([item])
      } else {
        await navigator.clipboard.writeText(previewHtml.value)
      }
      return true
    } catch {
      return false
    }
  }

  function downloadHtm(): void {
    if (!previewHtml.value) return
    const blob = new Blob([previewHtml.value], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename.value || 'signature.htm'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const mailtoSupport = computed(() =>
    supportEmail.value ? `mailto:${supportEmail.value}` : '',
  )

  return {
    form,
    config,
    configLoading: computed(() => configQuery.isLoading.value),
    configError: computed(() => configQuery.isError.value),
    moduleEnabled,
    cityOptions,
    officePhoneOptions,
    languageOptions,
    deviceOptions,
    supportEmail,
    mailtoSupport,
    emailDomain,
    previewHtml,
    filename,
    generating,
    generated,
    generateError,
    isValid,
    generate,
    onMobileInput,
    onExtensionInput,
    copyHtml,
    downloadHtm,
  }
}
