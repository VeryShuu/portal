<template>
  <div class="login-split">
    <!-- Left: brand hero -->
    <aside
      class="login-hero"
      aria-hidden="true"
      :style="loginBgStyle"
    >
      <svg v-if="!loginBgUrl" class="login-hero__waves" viewBox="0 0 1440 800" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="w1" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#143a66" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="#4a90c4" stop-opacity="0.08"/>
          </linearGradient>
        </defs>
        <path fill="url(#w1)" d="M0,520 C240,600 480,440 720,480 C960,520 1200,640 1440,560 L1440,800 L0,800 Z"/>
        <path fill="rgba(255,255,255,0.04)" d="M0,600 C240,680 480,540 720,580 C960,620 1200,720 1440,660 L1440,800 L0,800 Z"/>
        <path fill="rgba(216,38,44,0.08)" d="M0,720 C360,780 720,700 1080,740 C1260,760 1440,720 1440,720 L1440,800 L0,800 Z"/>
      </svg>

      <div class="login-hero__content">
        <div class="login-hero__brand">
          <div class="login-hero__logo">
            <svg viewBox="0 0 40 40" width="36" height="36" aria-hidden="true">
              <path d="M6 28 C 14 16, 26 16, 34 28" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/>
              <path d="M4 34 C 14 22, 26 22, 36 34" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" opacity="0.65"/>
              <circle cx="30" cy="12" r="4" fill="#d8262c"/>
            </svg>
          </div>
          <div class="login-hero__brand-text">{{ portalName }}</div>
        </div>

        <div class="login-hero__quote">
          <h1 class="login-hero__slogan">{{ portalTagline || t('auth.slogan') }}</h1>
          <p class="login-hero__sub">{{ t('auth.sloganSub') }}</p>
        </div>

        <div class="login-hero__footer">
          {{ t('auth.heroCopyright', { year: currentYear }) }}
        </div>
      </div>
    </aside>

    <!-- Right: form -->
    <main class="login-form-col">
      <div class="login-form">
        <div class="login-form__lang">
          <button type="button" class="lang-btn" :class="{ active: locale === 'ru' }" @click="setLang('ru')">RU</button>
          <button type="button" class="lang-btn" :class="{ active: locale === 'en' }" @click="setLang('en')">EN</button>
        </div>

        <h2 class="login-form__title">{{ t('auth.loginTitle') }}</h2>
        <p class="login-form__lead">{{ t('auth.sloganSub') }}</p>

        <n-spin v-if="!authConfig" size="medium" style="margin:32px auto;display:block" />

        <template v-else>
          <n-alert
            v-if="configError"
            type="warning"
            :title="t('auth.backendUnavailableTitle')"
            style="margin-bottom:14px"
          >
            {{ t('auth.backendUnavailable') }}
          </n-alert>
          <n-button
            v-if="authConfig.keycloak_enabled"
            type="primary"
            block
            size="large"
            :loading="ssoLoading"
            @click="loginSSO"
          >
            <template #icon>
              <n-icon><KeyOutline /></n-icon>
            </template>
            {{ t('auth.loginSSO') }}
          </n-button>

          <template v-if="authConfig.local_auth_enabled">
            <div v-if="authConfig.keycloak_enabled" class="divider">
              <span>{{ t('auth.orLocalLogin') }}</span>
            </div>

            <n-alert
              v-if="error"
              type="error"
              :title="t('errors.loginFailed')"
              closable
              style="margin-bottom:14px"
              @close="error = null"
            >
              {{ error }}
            </n-alert>

            <n-form ref="formRef" :model="form" :rules="rules" label-placement="top" @keyup.enter="loginLocal">
              <n-form-item path="email" :label="t('users.fields.email')">
                <n-input
                  v-model:value="form.email"
                  :placeholder="t('auth.emailPlaceholder')"
                  type="text"
                  autocomplete="email"
                  :input-props="{ autocomplete: 'email' }"
                />
              </n-form-item>
              <n-form-item path="password" :label="t('auth.passwordLabel')">
                <n-input
                  v-model:value="form.password"
                  type="password"
                  :placeholder="t('auth.passwordPlaceholder')"
                  show-password-on="click"
                  :input-props="{ autocomplete: 'current-password' }"
                />
              </n-form-item>
            </n-form>

            <n-button
              block
              size="large"
              :loading="localLoading"
              :disabled="!form.email || !form.password"
              @click="loginLocal"
            >
              {{ t('auth.loginLocal') }}
            </n-button>
          </template>

          <n-alert
            v-if="!authConfig.keycloak_enabled && !authConfig.local_auth_enabled"
            type="warning"
          >
            {{ t('auth.noAuthMethod') }}
          </n-alert>
        </template>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { loadLocale, type AppLocale } from '@/i18n'
import {
  NButton, NForm, NFormItem, NInput, NAlert, NIcon, NSpin,
  type FormInst, type FormRules,
} from 'naive-ui'
import { KeyOutline } from '@vicons/ionicons5'
import { localLogin, getSSOLoginUrl } from '../api/auth'
import { api } from '../api/index'
import { useAuthStore } from '../stores/auth'
import { useBrandingStore } from '../stores/branding'

const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const branding = useBrandingStore()

const formRef = ref<FormInst | null>(null)
const ssoLoading = ref(false)
const localLoading = ref(false)
const error = ref<string | null>(null)

const authConfig = ref<{ local_auth_enabled: boolean; keycloak_enabled: boolean } | null>(null)
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
    authConfig.value = await api<{ local_auth_enabled: boolean; keycloak_enabled: boolean }>('/auth/config')
  } catch {
    configError.value = true
    authConfig.value = { local_auth_enabled: true, keycloak_enabled: true }
  }
})

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
// P1-23: must start with single "/" — reject "//evil.tld", "/\\evil", "javascript:" etc.
const SAFE_REDIRECT = /^\/(?![/\\])[A-Za-z0-9_\-./?#&=%@:+,~!]*$/
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
      error.value = t('auth.useSSO')
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
</script>

<style scoped>
.login-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 100vh;
  background: var(--color-bg);
}

/* === Left hero === */
.login-hero {
  position: relative;
  overflow: hidden;
  background: var(--gradient-hero);
  color: #fff;
  display: flex;
  align-items: stretch;
}
.login-hero__waves {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.login-hero__content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 40px 56px;
  width: 100%;
}

.login-hero__brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.login-hero__logo {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.18);
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-hero__brand-text {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.9);
}

.login-hero__quote {
  max-width: 480px;
}
.login-hero__slogan {
  font-size: 40px;
  line-height: 1.1;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 0 0 14px;
  color: #fff;
}
.login-hero__sub {
  font-size: 16px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.78);
  margin: 0;
}

.login-hero__footer {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
  letter-spacing: 0.04em;
}

/* === Right form === */
.login-form-col {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 24px;
  background: linear-gradient(180deg, var(--color-surface) 0%, var(--color-brand-ice) 100%);
  position: relative;
}
.login-form {
  width: 100%;
  max-width: 400px;
  position: relative;
}
.login-form__lang {
  position: absolute;
  top: -16px;
  right: 0;
  display: flex;
  gap: 4px;
}
.lang-btn {
  font-family: inherit;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--t-fast);
}
.lang-btn:hover {
  color: var(--color-brand-navy);
  border-color: var(--color-brand-sky);
}
.lang-btn.active {
  background: var(--color-brand-navy);
  color: #fff;
  border-color: var(--color-brand-navy);
}

.login-form__title {
  margin: 0 0 6px;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: var(--color-text);
}
.login-form__lead {
  margin: 0 0 24px;
  color: var(--color-text-muted);
  font-size: 14px;
  line-height: 1.5;
}

.divider {
  display: flex;
  align-items: center;
  margin: 20px 0;
  color: var(--color-text-subtle);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  gap: 12px;
}
.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--color-border);
}

/* === Responsive === */
@media (max-width: 900px) {
  .login-split { grid-template-columns: 1fr; }
  .login-hero { min-height: 240px; }
  .login-hero__content { padding: 28px 32px; }
  .login-hero__slogan { font-size: 28px; }
  .login-hero__sub { font-size: 14px; }
}
@media (max-width: 480px) {
  .login-form-col { padding: 24px 16px; }
  .login-hero__content { padding: 20px; }
}
</style>
