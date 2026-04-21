<template>
  <div class="login-wrap">
    <n-card class="login-card" :title="t('auth.loginTitle')">
      <n-space vertical :size="16">
        <div class="logo-row">
          <n-icon size="48" color="var(--primary-color)">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </n-icon>
          <h2 style="margin:0">{{ t('app.title') }}</h2>
        </div>

        <n-button
          v-if="authConfig.keycloak_enabled"
          type="primary"
          block
          size="large"
          :loading="ssoLoading"
          @click="loginSSO"
        >
          {{ t('auth.loginSSO') }}
        </n-button>

        <template v-if="authConfig.local_auth_enabled">
          <n-divider v-if="authConfig.keycloak_enabled">{{ t('auth.orLocalLogin') }}</n-divider>

          <n-alert v-if="error" type="error" :title="t('errors.loginFailed')" closable @close="error = null">
            {{ error }}
          </n-alert>

          <n-form ref="formRef" :model="form" :rules="rules" label-placement="top" @keyup.enter="loginLocal">
            <n-form-item path="email" :label="t('users.fields.email')">
              <n-input
                v-model:value="form.email"
                :placeholder="t('auth.emailPlaceholder')"
                type="text"
                autocomplete="username"
                :input-props="{ autocomplete: 'username' }"
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

        <n-alert v-if="!authConfig.keycloak_enabled && !authConfig.local_auth_enabled" type="warning">
          {{ t('auth.noAuthMethod') }}
        </n-alert>
      </n-space>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  NCard, NButton, NForm, NFormItem, NInput, NDivider, NSpace, NAlert, NIcon,
  type FormInst, type FormRules,
} from 'naive-ui'
import { localLogin, getSSOLoginUrl } from '../api/auth'
import { api } from '../api/index'
import { useAuthStore } from '../stores/auth'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const formRef = ref<FormInst | null>(null)
const ssoLoading = ref(false)
const localLoading = ref(false)
const error = ref<string | null>(null)

const authConfig = ref({ local_auth_enabled: true, keycloak_enabled: true })

onMounted(async () => {
  try {
    const cfg = await api<{ local_auth_enabled: boolean; keycloak_enabled: boolean }>('/auth/config')
    authConfig.value = cfg
  } catch {
    // keep defaults
  }
})

const form = ref({ email: '', password: '' })

const rules: FormRules = {
  email: [{ required: true, type: 'email', message: t('auth.emailRequired'), trigger: 'blur' }],
  password: [{ required: true, message: t('auth.passwordRequired'), trigger: 'blur' }],
}

const rawRedirect = route.query.redirect as string
const redirectTo = rawRedirect && rawRedirect.startsWith('/') && !rawRedirect.startsWith('/api/') && !rawRedirect.startsWith('/realms/')
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
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--body-color);
  padding: 16px;
}

.login-card {
  width: 100%;
  max-width: 420px;
}

.logo-row {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
  margin-bottom: 8px;
}
</style>
