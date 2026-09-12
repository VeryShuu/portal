import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { loadLocale, type AppLocale } from '@/i18n'
import { type FormInst, type FormRules } from 'naive-ui'
import { localLogin, getSSOLoginUrl } from '../api/auth'
import { useAuthStore } from '../stores/auth'

const SAFE_REDIRECT = /^\/(?![/\\])[A-Za-z0-9_\-./?#&=%@:+,~!]*$/

export function useLoginForm() {
  const { t, locale } = useI18n()
  const router = useRouter()
  const route = useRoute()
  const auth = useAuthStore()

  const formRef = ref<FormInst | null>(null)
  const ssoLoading = ref(false)
  const localLoading = ref(false)
  const error = ref<string | null>(null)

  const form = ref({ email: '', password: '' })

  const rules: FormRules = {
    email: [
      { required: true, message: t('auth.emailRequired'), trigger: 'blur' },
      {
        trigger: 'blur',
        validator: (_rule: unknown, value: string) => {
          if (!value) return true
          if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value)) {
            return new Error(t('auth.emailInvalid'))
          }
          return true
        },
      },
    ],
    password: [{ required: true, message: t('auth.passwordRequired'), trigger: 'blur' }],
  }

  const rawRedirect = route.query.redirect as string
  const redirectTo = rawRedirect
    && SAFE_REDIRECT.test(rawRedirect)
    && !rawRedirect.startsWith('/api/')
    && !rawRedirect.startsWith('/realms/')
    ? rawRedirect
    : '/'

  function loginSSO() {
    ssoLoading.value = true
    window.location.href = getSSOLoginUrl(redirectTo)
  }

  async function loginLocal() {
    error.value = null
    try {
      await formRef.value?.validate()
    } catch {
      return
    }
    localLoading.value = true
    try {
      await localLogin(form.value.email, form.value.password)
      await auth.loadUser()
      router.push(redirectTo)
    } catch (err: unknown) {
      const e = err as { status?: number; body?: { detail?: string } }
      if (e?.status === 403) {
        const detail = e?.body?.detail ?? ''
        error.value = detail === 'Local authentication is disabled'
          ? t('auth.localAuthDisabled')
          : t('auth.useSSO')
      } else if (e?.status === 429) {
        error.value = t('auth.rateLimited')
      } else {
        error.value = t('auth.invalidCredentials')
      }
    } finally {
      localLoading.value = false
    }
  }

  async function setLang(lang: AppLocale) {
    await loadLocale(lang)
    locale.value = lang
    localStorage.setItem('lang', lang)
  }

  return { formRef, ssoLoading, localLoading, error, form, rules, redirectTo, locale, loginSSO, loginLocal, setLang }
}
