<template>
  <div class="branding-wrap">
    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.email.serverTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.email.serverHint') }}
      </div>
      <n-form
        :model="emailForm"
        label-placement="top"
      >
        <div class="branding-fields">
          <div class="email-row-2">
            <n-form-item
              :label="t('admin.email.host')"
              style="margin-bottom:0;flex:1"
            >
              <n-input
                v-model:value="emailForm.host"
                :placeholder="t('admin.email.hostPlaceholder')"
              />
            </n-form-item>
            <n-form-item
              :label="t('admin.email.port')"
              style="margin-bottom:0;width:110px"
            >
              <n-input-number
                v-model:value="emailForm.port"
                :min="1"
                :max="65535"
                style="width:100%"
              />
            </n-form-item>
          </div>
          <n-form-item
            :label="t('admin.email.fromAddress')"
            style="margin-bottom:0"
          >
            <n-input
              v-model:value="emailForm.from_address"
              :placeholder="t('admin.email.fromAddressPlaceholder')"
            />
          </n-form-item>
          <div class="email-row-2">
            <n-form-item
              :label="t('admin.email.username')"
              style="margin-bottom:0;flex:1"
            >
              <n-input
                v-model:value="emailForm.username"
                :placeholder="t('admin.email.usernamePlaceholder')"
                clearable
                :input-props="{ autocomplete: 'username' }"
              />
            </n-form-item>
            <n-form-item
              :label="t('admin.email.password')"
              style="margin-bottom:0;flex:1"
            >
              <n-input
                v-model:value="emailForm.password"
                type="password"
                show-password-on="click"
                :placeholder="emailPasswordSet ? t('admin.email.passwordKeep') : t('admin.email.passwordPlaceholder')"
                clearable
                :input-props="{ autocomplete: 'new-password' }"
              />
            </n-form-item>
          </div>
          <n-form-item
            :label="t('admin.email.encryption')"
            style="margin-bottom:0"
          >
            <n-radio-group v-model:value="encryption">
              <n-radio value="none">
                {{ t('admin.email.encryptionNone') }}
              </n-radio>
              <n-radio value="tls">
                TLS
              </n-radio>
              <n-radio value="starttls">
                STARTTLS
              </n-radio>
            </n-radio-group>
          </n-form-item>
        </div>
      </n-form>
      <div class="email-actions">
        <n-button
          type="primary"
          :loading="emailSaving"
          @click="saveEmailSettings"
        >
          {{ t('common.save') }}
        </n-button>
        <n-button
          :loading="emailTesting"
          @click="openTestEmailModal"
        >
          {{ t('admin.email.sendTest') }}
        </n-button>
      </div>
    </div>

    <!-- Общий IMAP-приёмник портала (ADR-048): используется модулями (erp_sync). -->
    <div class="branding-section">
      <div class="branding-section__title">
        {{ t('admin.email.imapTitle') }}
      </div>
      <div class="branding-section__hint">
        {{ t('admin.email.imapHint') }}
      </div>
      <n-form
        :model="emailForm"
        label-placement="top"
      >
        <div class="branding-fields">
          <div class="email-row-2">
            <n-form-item
              :label="t('admin.email.imapHost')"
              style="margin-bottom:0;flex:1"
            >
              <n-input
                v-model:value="emailForm.imap_host"
                :placeholder="t('admin.email.imapHostPlaceholder')"
              />
            </n-form-item>
            <n-form-item
              :label="t('admin.email.imapPort')"
              style="margin-bottom:0;width:110px"
            >
              <n-input-number
                v-model:value="emailForm.imap_port"
                :min="1"
                :max="65535"
                style="width:100%"
              />
            </n-form-item>
          </div>
          <n-form-item
            :label="t('admin.email.imapUsername')"
            style="margin-bottom:0"
          >
            <n-input
              v-model:value="emailForm.imap_username"
              :placeholder="t('admin.email.imapUsernamePlaceholder')"
              clearable
              :input-props="{ autocomplete: 'username' }"
            />
          </n-form-item>
          <n-form-item
            :label="t('admin.email.imapPassword')"
            style="margin-bottom:0"
          >
            <n-input
              v-model:value="emailForm.imap_password"
              type="password"
              show-password-on="click"
              :placeholder="imapPasswordSet ? t('admin.email.passwordKeep') : t('admin.email.passwordPlaceholder')"
              clearable
              :input-props="{ autocomplete: 'new-password' }"
            />
          </n-form-item>
          <div class="email-row-2">
            <n-form-item
              :label="t('admin.email.imapFolder')"
              style="margin-bottom:0;flex:1"
            >
              <n-input
                v-model:value="emailForm.imap_folder"
                placeholder="INBOX"
              />
            </n-form-item>
            <n-form-item
              :label="t('admin.email.imapUseSsl')"
              style="margin-bottom:0;width:110px"
            >
              <n-switch v-model:value="emailForm.imap_use_ssl" />
            </n-form-item>
          </div>
        </div>
      </n-form>
      <div
        v-if="imapTestResult"
        class="kc-test-result"
        :class="imapTestResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'"
      >
        <div class="kc-test-result__title">
          {{ imapTestResult.ok ? t('admin.email.imapTestOk') : t('admin.email.imapTestFail') }}
        </div>
        <div
          v-if="imapTestResult.detail"
          class="kc-test-result__details"
        >
          {{ imapTestResult.detail }}
        </div>
      </div>
      <div class="email-actions">
        <n-button
          :loading="imapTesting"
          :disabled="!imapPasswordSet && !emailForm.imap_password"
          @click="testImapConnection"
        >
          {{ t('admin.email.imapTest') }}
        </n-button>
      </div>
    </div>

    <n-modal
      v-model:show="testEmailModalOpen"
      :title="t('admin.email.testTitle')"
      preset="card"
      style="width:420px;max-width:94vw"
      :mask-closable="false"
    >
      <n-form-item :label="t('admin.email.testTo')">
        <n-input
          v-model:value="testEmailAddress"
          :placeholder="t('admin.email.testToPlaceholder')"
        />
      </n-form-item>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="testEmailModalOpen = false">
            {{ t('common.cancel') }}
          </n-button>
          <n-button
            type="primary"
            :loading="emailTesting"
            @click="sendTestEmail"
          >
            {{ t('admin.email.sendTestBtn') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NInputNumber, NForm, NFormItem, NRadioGroup, NRadio, NModal, NSwitch, useMessage } from 'naive-ui'
import { api } from '../../../api'
import { useEmailSettingsQuery } from '../../../queries/admin'
import { useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from '../../../queries/keys'
import { parseApiError } from '../../../utils/parseApiError'

const { t } = useI18n()
const message = useMessage()
const qc = useQueryClient()

interface EmailFormType {
  host: string
  port: number
  from_address: string
  username: string
  password: string
  use_tls: boolean
  use_starttls: boolean
  // Общий IMAP-приёмник (ADR-048).
  imap_host: string
  imap_port: number
  imap_username: string
  imap_password: string
  imap_use_ssl: boolean
  imap_folder: string
}

const emailForm = ref<EmailFormType>({
  host: '',
  port: 25,
  from_address: '',
  username: '',
  password: '',
  use_tls: false,
  use_starttls: false,
  imap_host: '',
  imap_port: 993,
  imap_username: '',
  imap_password: '',
  imap_use_ssl: true,
  imap_folder: 'INBOX',
})
const emailPasswordSet = ref(false)
const imapPasswordSet = ref(false)
const emailSaving = ref(false)
const emailTesting = ref(false)
const imapTesting = ref(false)
const imapTestResult = ref<{ ok: boolean; detail?: string } | null>(null)
const testEmailModalOpen = ref(false)
const testEmailAddress = ref('')
const emailLoadError = ref(false)

const { data: emailSettingsData, isError: emailLoadFailed } = useEmailSettingsQuery()

watch(emailSettingsData, (data) => {
  if (data) {
    emailForm.value = {
      host: data.host,
      port: data.port,
      from_address: data.from_address,
      username: data.username,
      password: '',
      use_tls: data.use_tls,
      use_starttls: data.use_starttls,
      imap_host: data.imap_host,
      imap_port: data.imap_port,
      imap_username: data.imap_username,
      imap_password: '',
      imap_use_ssl: data.imap_use_ssl,
      imap_folder: data.imap_folder,
    }
    emailPasswordSet.value = data.password_set
    imapPasswordSet.value = data.imap_password_set
    emailLoadError.value = false
  }
}, { immediate: true })

watch(emailLoadFailed, (failed) => {
  if (failed) emailLoadError.value = true
})

type EncryptionMode = 'none' | 'tls' | 'starttls'
const encryption = computed<EncryptionMode>({
  get() {
    if (emailForm.value.use_tls) return 'tls'
    if (emailForm.value.use_starttls) return 'starttls'
    return 'none'
  },
  set(v: EncryptionMode) {
    emailForm.value.use_tls = v === 'tls'
    emailForm.value.use_starttls = v === 'starttls'
  },
})

async function saveEmailSettings() {
  if (emailLoadError.value) {
    message.error(t('admin.email.loadFailedGuard'))
    return
  }
  emailSaving.value = true
  try {
    const payload = {
      ...emailForm.value,
      password: emailForm.value.password || null,
      // IMAP-пароль — write-only: null/'***' = оставить прежний.
      imap_password: emailForm.value.imap_password || null,
    }
    const data = await api<{
      host: string; port: number; from_address: string; username: string; password_set: boolean
      use_tls: boolean; use_starttls: boolean
      imap_host: string; imap_port: number; imap_use_ssl: boolean; imap_username: string
      imap_password_set: boolean; imap_folder: string
    }>(
      '/admin/email-settings',
      { method: 'PUT', body: payload },
    )
    emailPasswordSet.value = data.password_set
    imapPasswordSet.value = data.imap_password_set
    emailForm.value.password = ''
    emailForm.value.imap_password = ''
    qc.invalidateQueries({ queryKey: queryKeys.admin.emailSettings() })
    message.success(t('admin.email.saved'))
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    emailSaving.value = false
  }
}

function openTestEmailModal() {
  testEmailModalOpen.value = true
}

// Простая RFC5322-совместимая email-проверка — достаточная для UX-валидации
// перед отправкой; авторитетная проверка остаётся на стороне SMTP-сервера.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

async function sendTestEmail() {
  const to = testEmailAddress.value.trim()
  if (!to) {
    message.warning(t('admin.email.testToRequired'))
    return
  }
  if (!EMAIL_RE.test(to)) {
    message.warning(t('admin.email.testToRequired'))
    return
  }
  emailTesting.value = true
  try {
    await api('/admin/email-settings/test', {
      method: 'POST',
      body: { to: testEmailAddress.value.trim() },
    })
    message.success(t('admin.email.testSent', { to: testEmailAddress.value }))
    testEmailModalOpen.value = false
  } catch (e) {
    message.error(parseApiError(e, t))
  } finally {
    emailTesting.value = false
  }
}

// Сначала сохраняем (чтобы тест шёл по актуальным настройкам), затем проверяем.
// Пароль write-only — если не введён, шлём null (сервер оставит прежний).
async function testImapConnection() {
  imapTesting.value = true
  imapTestResult.value = null
  try {
    await saveEmailSettings()
    const res = await api<{ ok: boolean; detail?: string }>(
      '/admin/email-settings/imap/test',
      { method: 'POST' },
    )
    imapTestResult.value = { ok: res.ok, detail: res.detail }
  } catch (e) {
    imapTestResult.value = { ok: false, detail: parseApiError(e, t) }
  } finally {
    imapTesting.value = false
  }
}


</script>

<style scoped>
@import '../admin-tabs.css';
</style>
