<template>
  <n-spin :show="isLoading">
    <n-form
      v-if="form"
      label-placement="top"
      :show-feedback="false"
    >
      <div class="kb-grid">
        <n-form-item :label="t('admin.helpdesk.mailbox.imapHost')">
          <n-input
            v-model:value="form.imap_host"
            :placeholder="'imap.company.local'"
          />
        </n-form-item>
        <n-form-item :label="t('admin.helpdesk.mailbox.imapPort')">
          <n-input-number
            v-model:value="form.imap_port"
            :min="1"
            :max="65535"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item :label="t('admin.helpdesk.mailbox.imapUsername')">
          <n-input
            v-model:value="form.imap_username"
            autocomplete="off"
          />
        </n-form-item>
        <n-form-item :label="t('admin.helpdesk.mailbox.imapPassword')">
          <n-input
            v-model:value="form.imap_password"
            type="password"
            show-password-on="click"
            :placeholder="
              passwordSet
                ? t('admin.helpdesk.mailbox.passwordKeep')
                : t('admin.helpdesk.mailbox.passwordPlaceholder')
            "
            :input-props="{ autocomplete: 'new-password' }"
          />
        </n-form-item>
        <n-form-item :label="t('admin.helpdesk.mailbox.imapFolder')">
          <n-input
            v-model:value="form.imap_folder"
            placeholder="INBOX"
          />
        </n-form-item>
        <n-form-item :label="t('admin.helpdesk.mailbox.pollInterval')">
          <n-input-number
            v-model:value="form.poll_interval_seconds"
            :min="30"
            :max="600"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item :label="t('admin.helpdesk.mailbox.supportAddress')">
          <n-input
            v-model:value="form.support_address"
            placeholder="support@company.local"
          />
        </n-form-item>
        <n-form-item :label="t('admin.helpdesk.mailbox.supportReplyTo')">
          <n-input
            v-model:value="form.support_reply_to"
            placeholder="(необязательно)"
          />
        </n-form-item>
      </div>

      <div class="helpdesk-mailbox__toggles">
        <n-checkbox v-model:checked="form.imap_use_ssl">
          {{ t('admin.helpdesk.mailbox.useSsl') }}
        </n-checkbox>
        <n-checkbox v-model:checked="form.delete_after_fetch">
          {{ t('admin.helpdesk.mailbox.deleteAfterFetch') }}
        </n-checkbox>
      </div>

      <div class="helpdesk-mailbox__section-title">
        {{ t('admin.helpdesk.mailbox.smtpTitle') }}
      </div>
      <div class="helpdesk-mailbox__hint">
        {{ t('admin.helpdesk.mailbox.smtpHint') }}
      </div>
      <div class="kb-grid">
        <n-form-item :label="t('admin.helpdesk.mailbox.smtpHost')">
          <n-input
            v-model:value="form.smtp_host"
            :placeholder="'smtp.company.local'"
          />
        </n-form-item>
        <n-form-item :label="t('admin.helpdesk.mailbox.smtpPort')">
          <n-input-number
            v-model:value="form.smtp_port"
            :min="1"
            :max="65535"
            style="width: 100%"
          />
        </n-form-item>
        <n-form-item :label="t('admin.helpdesk.mailbox.smtpUsername')">
          <n-input
            v-model:value="form.smtp_username"
            autocomplete="off"
          />
        </n-form-item>
        <n-form-item :label="t('admin.helpdesk.mailbox.smtpPassword')">
          <n-input
            v-model:value="form.smtp_password"
            type="password"
            show-password-on="click"
            :placeholder="
              smtpPasswordSet
                ? t('admin.helpdesk.mailbox.passwordKeep')
                : t('admin.helpdesk.mailbox.passwordPlaceholder')
            "
            :input-props="{ autocomplete: 'new-password' }"
          />
        </n-form-item>
      </div>
      <div class="helpdesk-mailbox__toggles">
        <n-checkbox v-model:checked="form.smtp_use_tls">
          {{ t('admin.helpdesk.mailbox.useTls') }}
        </n-checkbox>
        <n-checkbox v-model:checked="form.smtp_use_starttls">
          {{ t('admin.helpdesk.mailbox.useStarttls') }}
        </n-checkbox>
      </div>

      <div
        v-if="!configured"
        class="helpdesk-mailbox__notconfigured"
      >
        {{ t('admin.helpdesk.mailbox.notConfigured') }}
      </div>

      <div class="email-actions">
        <n-button
          type="primary"
          :loading="putMut.isPending.value"
          :disabled="!isDirty"
          @click="onSave"
        >
          {{ t('common.save') }}
        </n-button>
        <n-button
          :loading="testing"
          :disabled="!configured"
          @click="onTest"
        >
          {{ t('admin.helpdesk.mailbox.test') }}
        </n-button>
        <n-button
          :loading="testingSmtp"
          :disabled="!configured"
          @click="onTestSmtp"
        >
          {{ t('admin.helpdesk.mailbox.testSmtp') }}
        </n-button>
      </div>

      <div
        v-if="testResult"
        class="kc-test-result"
        :class="testResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'"
      >
        <div class="kc-test-result__title">
          {{
            testResult.ok
              ? t('admin.helpdesk.mailbox.testOk')
              : t('admin.helpdesk.mailbox.testFail')
          }}
        </div>
        <div
          v-if="testResult.detail || testResult.error"
          class="kc-test-result__details"
        >
          {{ testResult.detail || testResult.error }}
        </div>
      </div>

      <div
        v-if="smtpTestResult"
        class="kc-test-result"
        :class="smtpTestResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'"
      >
        <div class="kc-test-result__title">
          {{
            smtpTestResult.ok
              ? t('admin.helpdesk.mailbox.testSmtpOk')
              : t('admin.helpdesk.mailbox.testSmtpFail')
          }}
        </div>
        <div
          v-if="smtpTestResult.detail || smtpTestResult.error"
          class="kc-test-result__details"
        >
          {{ smtpTestResult.detail || smtpTestResult.error }}
        </div>
      </div>
    </n-form>
  </n-spin>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMessage, NSpin, NForm, NFormItem, NInput, NInputNumber, NCheckbox, NButton } from 'naive-ui'
import type { HelpdeskMailboxSettingsIn, HelpdeskMailboxTestResult } from '../../api/helpdesk'
import { testHelpdeskMailbox, testHelpdeskMailboxSmtp } from '../../api/helpdesk'
import { useHelpdeskMailboxQuery, usePutHelpdeskMailboxMutation } from '../../queries/helpdesk'
import { parseApiError } from '../../utils/parseApiError'

const { t } = useI18n()
const message = useMessage()

const { data, isLoading } = useHelpdeskMailboxQuery()
const putMut = usePutHelpdeskMailboxMutation()

interface MailboxFormState {
  imap_host: string
  imap_port: number
  imap_username: string
  imap_password: string | null
  imap_use_ssl: boolean
  imap_folder: string
  poll_interval_seconds: number
  delete_after_fetch: boolean
  support_address: string
  support_reply_to: string | null
  smtp_host: string | null
  smtp_port: number
  smtp_username: string | null
  smtp_password: string | null
  smtp_use_tls: boolean
  smtp_use_starttls: boolean
}

const EMPTY: MailboxFormState = {
  imap_host: '',
  imap_port: 993,
  imap_username: '',
  imap_password: null,
  imap_use_ssl: true,
  imap_folder: 'INBOX',
  poll_interval_seconds: 60,
  delete_after_fetch: false,
  support_address: '',
  support_reply_to: null,
  smtp_host: null,
  smtp_port: 25,
  smtp_username: null,
  smtp_password: null,
  smtp_use_tls: false,
  smtp_use_starttls: false,
}

const form = ref<MailboxFormState | null>(null)
const configured = ref(false)
const passwordSet = ref(false)
const smtpPasswordSet = ref(false)
const isDirty = ref(false)

// Заполняем форму из ответа (один раз + следим за изменениями формы для dirty).
watch(
  data,
  (d) => {
    if (!d) return
    configured.value = d.configured
    passwordSet.value = d.imap_password_set
    smtpPasswordSet.value = d.smtp_password_set
    form.value = {
      imap_host: d.imap_host ?? '',
      imap_port: d.imap_port,
      imap_username: d.imap_username ?? '',
      imap_password: null, // write-only: никогда не предзаполняем
      imap_use_ssl: d.imap_use_ssl,
      imap_folder: d.imap_folder,
      poll_interval_seconds: d.poll_interval_seconds,
      delete_after_fetch: d.delete_after_fetch,
      support_address: d.support_address ?? '',
      support_reply_to: d.support_reply_to ?? null,
      smtp_host: d.smtp_host,
      smtp_port: d.smtp_port,
      smtp_username: d.smtp_username,
      smtp_password: null, // write-only: никогда не предзаполняем
      smtp_use_tls: d.smtp_use_tls,
      smtp_use_starttls: d.smtp_use_starttls,
    }
    isDirty.value = false
  },
  { immediate: true },
)

watch(
  form,
  () => {
    if (form.value) isDirty.value = true
  },
  { deep: true },
)

function buildDto(): HelpdeskMailboxSettingsIn {
  const f = form.value ?? EMPTY
  // n-input-number отдаёт null при очистке поля; бэкенд требует int (default
  // применяется только к отсутствующему полю, не к null) → 422. Коалесцируем
  // к тем же дефолтам, что и в Pydantic-схеме HelpdeskMailboxSettingsIn.
  const dto: HelpdeskMailboxSettingsIn = {
    imap_host: f.imap_host,
    imap_port: f.imap_port ?? 993,
    imap_username: f.imap_username,
    imap_use_ssl: f.imap_use_ssl,
    imap_folder: f.imap_folder,
    poll_interval_seconds: f.poll_interval_seconds ?? 60,
    delete_after_fetch: f.delete_after_fetch,
    support_address: f.support_address,
    support_reply_to: f.support_reply_to,
    smtp_host: (f.smtp_host ?? '').trim() || null,
    smtp_port: f.smtp_port ?? 25,
    smtp_username: f.smtp_username || null,
    smtp_use_tls: f.smtp_use_tls,
    smtp_use_starttls: f.smtp_use_starttls,
  }
  // Пароль: передаём только если пользователь что-то ввёл. При создании
  // (configured=false) пароль обязателен на бэке.
  if (f.imap_password) {
    dto.imap_password = f.imap_password
  }
  // SMTP-пароль: write-only, опционален (SMTP-блок целиком опционален — fallback).
  if (f.smtp_password) {
    dto.smtp_password = f.smtp_password
  }
  return dto
}

async function onSave() {
  if (!form.value) return
  if (!configured.value && !form.value.imap_password) {
    message.error(t('admin.helpdesk.mailbox.passwordRequired'))
    return
  }
  try {
    await putMut.mutateAsync(buildDto())
    message.success(t('admin.modules.saved'))
    // После save бэкенд возвращает обновлённый out; query инвалидируется,
    // watch(data) снова выставит passwords=null.
    form.value.imap_password = null
    form.value.smtp_password = null
    isDirty.value = false
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

const testing = ref(false)
const testResult = ref<HelpdeskMailboxTestResult | null>(null)
async function onTest() {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await testHelpdeskMailbox()
  } catch (e) {
    testResult.value = { ok: false, error: parseApiError(e, t) }
  } finally {
    testing.value = false
  }
}

const testingSmtp = ref(false)
const smtpTestResult = ref<HelpdeskMailboxTestResult | null>(null)
async function onTestSmtp() {
  testingSmtp.value = true
  smtpTestResult.value = null
  try {
    smtpTestResult.value = await testHelpdeskMailboxSmtp()
  } catch (e) {
    smtpTestResult.value = { ok: false, error: parseApiError(e, t) }
  } finally {
    testingSmtp.value = false
  }
}
</script>

<style scoped>
.kb-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.helpdesk-mailbox__toggles {
  display: flex;
  gap: 24px;
  margin: 16px 0;
}
.helpdesk-mailbox__section-title {
  font-size: 15px;
  font-weight: 600;
  margin: 24px 0 4px;
}
.helpdesk-mailbox__hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}
.helpdesk-mailbox__notconfigured {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 12px;
}
.email-actions {
  display: flex;
  gap: 12px;
}
</style>
