import { computed, onMounted, ref } from 'vue'
import { useBrandingStore } from '../stores/branding'
import { api } from '../api/index'
import { useI18n } from 'vue-i18n'

interface AuthConfig {
  local_auth_enabled: boolean
  keycloak_enabled: boolean
}

export function useLoginConfig() {
  const { t } = useI18n()
  const branding = useBrandingStore()

  const authConfig = ref<AuthConfig | null>(null)
  const configError = ref(false)
  const loginBgUrl = ref<string | null>(null)

  const currentYear = computed(() => new Date().getFullYear())
  const portalName = computed(() => branding.settings.portal_name || t('app.title'))
  const portalTagline = computed(() => branding.settings.portal_tagline || t('auth.slogan'))
  const loginBgStyle = computed(() => {
    if (!loginBgUrl.value) return {}
    return {
      backgroundImage: `url('${loginBgUrl.value}')`,
      backgroundSize: 'cover',
      backgroundPosition: 'center',
    }
  })

  onMounted(async () => {
    if (branding.settings.has_login_bg) {
      loginBgUrl.value = `/api/v1/branding/login-bg?t=${Date.now()}`
    }
    try {
      authConfig.value = await api<AuthConfig>('/auth/config')
    } catch {
      configError.value = true
      authConfig.value = { local_auth_enabled: true, keycloak_enabled: true }
    }
  })

  return { authConfig, configError, loginBgUrl, loginBgStyle, currentYear, portalName, portalTagline }
}
