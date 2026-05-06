<template>
  <div class="login-split">
    <aside class="login-hero" aria-hidden="true" :style="loginBgStyle">
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

    <main class="login-form-col">
      <div class="login-form">
        <h2 class="login-form__title">{{ t('auth.error.title') }}</h2>

        <n-alert
          :type="alertType"
          :title="alertTitle"
          style="margin: 16px 0 24px"
        >
          {{ alertText }}
        </n-alert>

        <n-button type="primary" block size="large" @click="retry">
          {{ t('auth.error.retry') }}
        </n-button>

        <p class="admin-link">
          <router-link :to="{ path: '/auth/local' }">
            {{ t('auth.error.adminLoginLink') }}
          </router-link>
        </p>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NButton, NAlert } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import { useBrandingStore } from '../stores/branding'

const { t } = useI18n()
const route = useRoute()
const auth = useAuthStore()
const branding = useBrandingStore()

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

type Reason = 'sso_failed' | 'logged_out' | 'loop_detected' | 'keycloak_unavailable' | 'nonce_mismatch'

const reason = computed<Reason>(() => {
  const r = (route.query.reason as string) || 'sso_failed'
  if (['sso_failed', 'logged_out', 'loop_detected', 'keycloak_unavailable', 'nonce_mismatch'].includes(r)) {
    return r as Reason
  }
  return 'sso_failed'
})

const alertType = computed<'success' | 'warning' | 'error' | 'info'>(() => {
  if (reason.value === 'logged_out') return 'success'
  if (reason.value === 'loop_detected' || reason.value === 'keycloak_unavailable') return 'warning'
  return 'error'
})

const alertTitle = computed(() => {
  switch (reason.value) {
    case 'logged_out': return t('auth.error.loggedOutTitle')
    case 'loop_detected': return t('auth.error.loopDetectedTitle')
    case 'keycloak_unavailable': return t('auth.error.keycloakUnavailableTitle')
    default: return t('auth.error.ssoFailedTitle')
  }
})

const alertText = computed(() => {
  switch (reason.value) {
    case 'logged_out': return t('auth.error.loggedOut')
    case 'loop_detected': return t('auth.error.loopDetected')
    case 'keycloak_unavailable': return t('auth.error.keycloakUnavailable')
    case 'nonce_mismatch':
    case 'sso_failed':
    default: return t('auth.error.ssoFailed')
  }
})

// При монтировании НЕ очищаем sso_failed (иначе случится авто-редирект на главной).
onMounted(() => {
  if (branding.settings.has_login_bg) {
    loginBgUrl.value = `/api/v1/branding/login-bg?t=${Date.now()}`
  }
})

function retry() {
  auth.clearSSOState()
  const rawRedirect = (route.query.redirect as string) || '/'
  const SAFE = /^\/(?![/\\])[A-Za-z0-9_\-./?#&=%@:+,~!]*$/
  const redirectTo = rawRedirect && SAFE.test(rawRedirect)
    && !rawRedirect.startsWith('/api/')
    && !rawRedirect.startsWith('/realms/')
    ? rawRedirect
    : '/'
  window.location.href = '/api/v1/auth/login?redirect=' + encodeURIComponent(redirectTo)
}
</script>

<style scoped>
.login-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 100vh;
  background: var(--color-bg);
}
.login-hero {
  position: relative; overflow: hidden;
  background: var(--gradient-hero); color: #fff;
  display: flex; align-items: stretch;
}
.login-hero__waves { position: absolute; inset: 0; width: 100%; height: 100%; }
.login-hero__content {
  position: relative; z-index: 1;
  display: flex; flex-direction: column; justify-content: space-between;
  padding: 40px 56px; width: 100%;
}
.login-hero__brand { display: flex; align-items: center; gap: 12px; }
.login-hero__logo {
  width: 44px; height: 44px;
  border-radius: var(--radius-md);
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.18);
  display: flex; align-items: center; justify-content: center;
}
.login-hero__brand-text {
  font-size: 15px; font-weight: 700; letter-spacing: 0.02em;
  text-transform: uppercase; color: rgba(255,255,255,0.9);
}
.login-hero__quote { max-width: 480px; }
.login-hero__slogan {
  font-size: 40px; line-height: 1.1; font-weight: 800;
  letter-spacing: -0.02em; margin: 0 0 14px; color: #fff;
}
.login-hero__sub {
  font-size: 16px; line-height: 1.6;
  color: rgba(255,255,255,0.78); margin: 0;
}
.login-hero__footer {
  font-size: 12px; color: rgba(255,255,255,0.55); letter-spacing: 0.04em;
}

.login-form-col {
  display: flex; align-items: center; justify-content: center;
  padding: 32px 24px;
  background: linear-gradient(180deg, var(--color-surface) 0%, var(--color-brand-ice) 100%);
}
.login-form { width: 100%; max-width: 400px; }
.login-form__title {
  margin: 0 0 6px; font-size: 26px; font-weight: 800;
  letter-spacing: -0.02em; color: var(--color-text);
}
.admin-link {
  margin: 28px 0 0;
  text-align: center;
  font-size: 12px;
  color: var(--color-text-subtle);
}
.admin-link a {
  color: var(--color-text-muted);
  text-decoration: none;
  border-bottom: 1px dotted var(--color-text-subtle);
}
.admin-link a:hover {
  color: var(--color-brand-navy);
}

@media (max-width: 900px) {
  .login-split { grid-template-columns: 1fr; }
  .login-hero { min-height: 240px; }
  .login-hero__content { padding: 28px 32px; }
  .login-hero__slogan { font-size: 28px; }
}
@media (max-width: 480px) {
  .login-form-col { padding: 24px 16px; }
  .login-hero__content { padding: 20px; }
}
</style>
