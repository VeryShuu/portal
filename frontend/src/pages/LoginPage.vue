<template>
  <div class="login-split">
    <!-- Left: brand hero -->
    <aside
      class="login-hero"
      aria-hidden="true"
      :style="loginBgStyle"
    >
      <svg
        v-if="!loginBgUrl"
        class="login-hero__waves"
        viewBox="0 0 1440 800"
        preserveAspectRatio="xMidYMid slice"
      >
        <defs>
          <linearGradient
            id="w1"
            x1="0"
            y1="0"
            x2="1"
            y2="1"
          >
            <stop
              offset="0%"
              stop-color="#143a66"
              stop-opacity="0.35"
            />
            <stop
              offset="100%"
              stop-color="#4a90c4"
              stop-opacity="0.08"
            />
          </linearGradient>
        </defs>
        <path
          fill="url(#w1)"
          d="M0,520 C240,600 480,440 720,480 C960,520 1200,640 1440,560 L1440,800 L0,800 Z"
        />
        <path
          fill="rgba(255,255,255,0.04)"
          d="M0,600 C240,680 480,540 720,580 C960,620 1200,720 1440,660 L1440,800 L0,800 Z"
        />
        <path
          fill="rgba(216,38,44,0.08)"
          d="M0,720 C360,780 720,700 1080,740 C1260,760 1440,720 1440,720 L1440,800 L0,800 Z"
        />
      </svg>

      <div class="login-hero__content">
        <div class="login-hero__brand">
          <div class="login-hero__logo">
            <svg
              viewBox="0 0 40 40"
              width="36"
              height="36"
              aria-hidden="true"
            >
              <path
                d="M6 28 C 14 16, 26 16, 34 28"
                fill="none"
                stroke="#fff"
                stroke-width="2.5"
                stroke-linecap="round"
              />
              <path
                d="M4 34 C 14 22, 26 22, 36 34"
                fill="none"
                stroke="#fff"
                stroke-width="2.5"
                stroke-linecap="round"
                opacity="0.65"
              />
              <circle
                cx="30"
                cy="12"
                r="4"
                fill="#d8262c"
              />
            </svg>
          </div>
          <div class="login-hero__brand-text">
            {{ portalName }}
          </div>
        </div>

        <div class="login-hero__quote">
          <h1 class="login-hero__slogan">
            {{ portalTagline || t('auth.slogan') }}
          </h1>
          <p class="login-hero__sub">
            {{ t('auth.sloganSub') }}
          </p>
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
          <button
            type="button"
            class="lang-btn"
            :class="{ active: locale === 'ru' }"
            @click="setLang('ru')"
          >
            RU
          </button>
          <button
            type="button"
            class="lang-btn"
            :class="{ active: locale === 'en' }"
            @click="setLang('en')"
          >
            EN
          </button>
        </div>

        <h2 class="login-form__title">
          {{ t('auth.loginTitle') }}
        </h2>
        <p class="login-form__lead">
          {{ t('auth.sloganSub') }}
        </p>

        <n-spin
          v-if="!authConfig"
          size="medium"
          style="margin:32px auto;display:block"
        />

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
            <div
              v-if="authConfig.keycloak_enabled"
              class="divider"
            >
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

            <n-form
              ref="formRef"
              :model="form"
              :rules="rules"
              label-placement="top"
              @keyup.enter="loginLocal"
            >
              <n-form-item
                path="email"
                :label="t('users.fields.email')"
              >
                <n-input
                  v-model:value="form.email"
                  :placeholder="t('auth.emailPlaceholder')"
                  type="text"
                  autocomplete="email"
                  :input-props="{ autocomplete: 'email' }"
                />
              </n-form-item>
              <n-form-item
                path="password"
                :label="t('auth.passwordLabel')"
              >
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
import { useI18n } from 'vue-i18n'
import {
  NButton, NForm, NFormItem, NInput, NAlert, NIcon, NSpin,
} from 'naive-ui'
import { KeyOutline } from '@vicons/ionicons5'
import { useLoginConfig } from '../composables/useLoginConfig'
import { useLoginForm } from '../composables/useLoginForm'

const { t } = useI18n()
const { authConfig, configError, loginBgUrl, loginBgStyle, currentYear, portalName, portalTagline } = useLoginConfig()
const { formRef, ssoLoading, localLoading, error, form, rules, locale, loginSSO, loginLocal, setLang } = useLoginForm()
</script>

<style scoped>
.login-form-col { position: relative; }
.login-form { position: relative; }
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
.lang-btn:hover { color: var(--color-brand-navy); border-color: var(--color-brand-sky); }
.lang-btn.active { background: var(--color-brand-navy); color: #fff; border-color: var(--color-brand-navy); }
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
</style>
