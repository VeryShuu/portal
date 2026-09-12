<template>
  <div class="learn-login">
    <n-card class="learn-login__card">
      <h1 class="learn-login__title">
        {{ step === 'email' ? t('learning.learn.loginTitle') : t('learning.learn.codeTitle') }}
      </h1>
      <p class="learn-login__hint">
        {{
          step === 'email'
            ? t('learning.learn.loginHint')
            : t('learning.learn.codeHint', { email: form.email })
        }}
      </p>

      <!-- Шаг 1: email → код уходит письмом (passwordless, миграция 113) -->
      <n-form
        v-if="step === 'email'"
        ref="formRef"
        :model="form"
        :rules="rules"
        :show-label="false"
        @submit.prevent="onRequestCode"
      >
        <n-form-item
          path="email"
          :label="t('learning.learn.email')"
        >
          <n-input
            v-model:value="form.email"
            :placeholder="t('learning.learn.email')"
            :input-props="{ autocomplete: 'username', type: 'email' }"
            :disabled="busy"
          />
        </n-form-item>

        <n-button
          attr-type="submit"
          type="primary"
          block
          :loading="busy"
          :disabled="!form.email"
        >
          {{ t('learning.learn.loginSubmit') }}
        </n-button>
      </n-form>

      <!-- Шаг 2: код из письма -->
      <n-form
        v-else
        ref="codeFormRef"
        :model="form"
        :rules="codeRules"
        :show-label="false"
        @submit.prevent="onVerify"
      >
        <n-form-item
          path="code"
          :label="t('learning.learn.codeLabel')"
        >
          <n-input
            ref="codeInputRef"
            v-model:value="form.code"
            :placeholder="t('learning.learn.codePlaceholder')"
            :input-props="{ autocomplete: 'one-time-code', inputmode: 'numeric' }"
            :disabled="busy"
            :maxlength="6"
          />
        </n-form-item>

        <n-button
          attr-type="submit"
          type="primary"
          block
          :loading="busy"
          :disabled="form.code.length !== 6"
        >
          {{ t('learning.learn.verifySubmit') }}
        </n-button>

        <div class="learn-login__links">
          <n-button
            quaternary
            size="small"
            :disabled="resendIn > 0 || resendBusy"
            :loading="resendBusy"
            @click="onResend"
          >
            {{
              resendIn > 0
                ? t('learning.learn.resendIn', { seconds: resendIn })
                : t('learning.learn.resend')
            }}
          </n-button>
          <n-button
            quaternary
            size="small"
            :disabled="busy || resendBusy"
            @click="onEditEmail"
          >
            {{ t('learning.learn.changeEmail') }}
          </n-button>
        </div>
      </n-form>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import type { FormInst, FormRules } from 'naive-ui'
import { NButton, NCard, NForm, NFormItem, NInput } from 'naive-ui'
import { learningRequestCode, learningVerifyCode } from '../../api/learningAuth'
import { fetchMyCourses } from '../../api/learning'

const RESEND_COOLDOWN_SECONDS = 60

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const message = useMessage()

const formRef = ref<FormInst | null>(null)
const codeFormRef = ref<FormInst | null>(null)
const busy = ref(false)
const resendBusy = ref(false)
const resendIn = ref(0)
const step = ref<'email' | 'code'>('email')
const form = reactive({ email: '', code: '' })

const rules: FormRules = {
  email: [{ required: true, message: t('learning.learn.emailRequired'), trigger: ['blur', 'input'] }],
}
const codeRules: FormRules = {
  code: [
    { required: true, message: t('learning.learn.codeRequired'), trigger: ['blur', 'input'] },
  ],
}

let resendTimer: ReturnType<typeof setInterval> | null = null
function startResendCooldown(): void {
  resendIn.value = RESEND_COOLDOWN_SECONDS
  stopResendTimer()
  resendTimer = setInterval(() => {
    resendIn.value -= 1
    if (resendIn.value <= 0) stopResendTimer()
  }, 1000)
}
function stopResendTimer(): void {
  if (resendTimer) {
    clearInterval(resendTimer)
    resendTimer = null
  }
}
onBeforeUnmount(stopResendTimer)

onMounted(async () => {
  // Уже есть валидная learner-сессия → форма входа не нужна.
  try {
    await fetchMyCourses()
    await router.push(redirectTarget())
  } catch {
    // 401 (нет сессии) — остаёмся на форме; иные ошибки тоже не блокируют вход.
  }
})

function redirectTarget(): string | { name: string } {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  return redirect.startsWith('/') ? redirect : { name: 'learning' }
}

function errorMessage(err: unknown): void {
  const status = (err as { status?: number })?.status
  if (status === 429) message.error(t('learning.learn.tooManyAttempts'))
  else message.error(t('learning.learn.genericError'))
}

async function requestCode(): Promise<void> {
  resendBusy.value = true
  try {
    // Ответ всегда ok — анти-enumeration: существует ли email, по API не узнать.
    await learningRequestCode(form.email.trim())
    message.success(t('learning.learn.codeSent'))
    step.value = 'code'
    startResendCooldown()
  } catch (err) {
    errorMessage(err)
  } finally {
    resendBusy.value = false
  }
}

async function onRequestCode(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await formRef.value?.validate()
    await requestCode()
  } catch {
    // ошибки валидации формы отображает сама форма
  } finally {
    busy.value = false
  }
}

async function onResend(): Promise<void> {
  await requestCode()
}

function onEditEmail(): void {
  form.code = ''
  step.value = 'email'
}

async function onVerify(): Promise<void> {
  if (busy.value) return
  try {
    await codeFormRef.value?.validate()
  } catch {
    return // ошибки валидации отображает сама форма
  }
  busy.value = true
  try {
    await learningVerifyCode(form.email.trim(), form.code)
    await router.push(redirectTarget())
  } catch (err) {
    const status = (err as { status?: number })?.status
    if (status === 400) {
      // единый отказ сервера: нет кода / неверный / истёк / попытки исчерпаны
      message.error(t('learning.learn.invalidCode'))
      form.code = ''
    } else {
      errorMessage(err)
    }
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.learn-login {
  display: flex;
  justify-content: center;
  padding-top: 8vh;
}

.learn-login__card {
  width: 100%;
  max-width: 400px;
}

.learn-login__title {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 600;
}

.learn-login__hint {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--text-secondary, #999);
}

.learn-login__links {
  margin-top: 14px;
  font-size: 13px;
  display: flex;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
