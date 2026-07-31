<template>
  <section class="branding-section">
    <h3 class="branding-section__title">
      {{ t('admin.erpSync.settings.title') }}
    </h3>
    <p class="branding-section__hint">
      {{ t('admin.erpSync.settings.hint') }}
    </p>

    <n-spin :show="isLoading">
      <n-form
        v-if="form"
        label-placement="top"
        :show-feedback="false"
      >
        <div class="kb-grid">
          <n-form-item :label="t('admin.erpSync.settings.enabled')">
            <n-switch v-model:value="form.enabled" />
          </n-form-item>
          <n-form-item :label="t('admin.erpSync.settings.pollEnabled')">
            <n-switch v-model:value="form.poll_enabled" />
            <span class="erp-sync__hint">{{ t('admin.erpSync.settings.pollEnabledHint') }}</span>
          </n-form-item>

          <n-form-item :label="t('admin.erpSync.settings.imapHost')">
            <n-input
              v-model:value="form.imap_host"
              placeholder="imap.company.local"
            />
          </n-form-item>
          <n-form-item :label="t('admin.erpSync.settings.imapPort')">
            <n-input-number
              v-model:value="form.imap_port"
              :min="1"
              :max="65535"
              style="width: 100%"
            />
          </n-form-item>

          <n-form-item :label="t('admin.erpSync.settings.imapUsername')">
            <n-input
              v-model:value="form.imap_username"
              placeholder="erp@company.local"
            />
          </n-form-item>
          <n-form-item :label="t('admin.erpSync.settings.imapFolder')">
            <n-input
              v-model:value="form.imap_folder"
              placeholder="INBOX"
            />
          </n-form-item>

          <n-form-item :label="t('admin.erpSync.settings.imapPassword')">
            <n-input
              v-model:value="form.imap_password"
              type="password"
              show-password-on="click"
              :placeholder="passwordSet
                ? t('admin.erpSync.settings.passwordKeep')
                : t('admin.erpSync.settings.passwordPlaceholder')"
              :input-props="{ autocomplete: 'new-password' }"
            />
          </n-form-item>
          <n-form-item :label="t('admin.erpSync.settings.imapUseSsl')">
            <n-switch v-model:value="form.imap_use_ssl" />
          </n-form-item>

          <n-form-item :label="t('admin.erpSync.settings.pollInterval')">
            <n-input-number
              v-model:value="form.poll_interval_seconds"
              :min="60"
              :max="3600"
              style="width: 100%"
            />
          </n-form-item>
          <n-form-item :label="t('admin.erpSync.settings.expectedInterval')">
            <n-input-number
              v-model:value="form.expected_interval_days"
              :min="1"
              :max="30"
              style="width: 100%"
            />
          </n-form-item>
        </div>

        <h4 class="erp-sync__subtitle">
          {{ t('admin.erpSync.settings.filtersTitle') }}
        </h4>
        <p class="erp-sync__hint">
          {{ t('admin.erpSync.settings.filtersHint') }}
        </p>
        <div class="kb-grid">
          <n-form-item :label="t('admin.erpSync.settings.subjectFilter')">
            <n-input
              v-model:value="form.mail_subject_filter"
              :placeholder="t('admin.erpSync.settings.subjectFilterPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('admin.erpSync.settings.senderFilter')">
            <n-input
              v-model:value="form.mail_sender_filter"
              placeholder="erp@company.local"
            />
          </n-form-item>
          <n-form-item :label="t('admin.erpSync.settings.attachmentFilter')">
            <n-input
              v-model:value="form.mail_attachment_filter"
              placeholder=".xlsx"
            />
          </n-form-item>
          <n-form-item :label="t('admin.erpSync.settings.notifyEmails')">
            <n-input
              v-model:value="notifyEmailsStr"
              :placeholder="t('admin.erpSync.settings.notifyEmailsPlaceholder')"
            />
          </n-form-item>
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
            :disabled="!passwordSet && !form.imap_password"
            @click="onTest"
          >
            {{ t('admin.erpSync.settings.test') }}
          </n-button>
        </div>

        <div
          v-if="testResult"
          class="kc-test-result"
          :class="testResult.ok ? 'kc-test-result--ok' : 'kc-test-result--fail'"
        >
          <div class="kc-test-result__title">
            {{ testResult.ok
              ? t('admin.erpSync.settings.testOk')
              : t('admin.erpSync.settings.testFail') }}
          </div>
          <div
            v-if="testResult.error"
            class="kc-test-result__details"
          >
            {{ testResult.error }}
          </div>
        </div>
      </n-form>
    </n-spin>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NForm, NFormItem, NInput, NInputNumber, NSpin, NSwitch, useMessage } from 'naive-ui'
import { parseApiError } from '../../utils/parseApiError'
import { testErpSync, type ErpSyncSettingsIn, type ErpSyncSettingsOut, type ErpSyncTestResult } from '../../api/erpSync'
import { useErpSyncSettingsQuery, usePutErpSyncSettingsMutation } from '../../queries/erpSync'

const { t } = useI18n()
const message = useMessage()

const { data, isLoading } = useErpSyncSettingsQuery()
const putMut = usePutErpSyncSettingsMutation()

interface FormState extends Omit<ErpSyncSettingsIn, 'notify_emails'> {
  imap_password: string | null
  notify_emails: string[] | null
}

const form = ref<FormState | null>(null)
const passwordSet = ref(false)
const isDirty = ref(false)
const notifyEmailsStr = ref('')

// Загрузка данных в форму.
watch(
  data,
  (d: ErpSyncSettingsOut | undefined) => {
    if (!d) return
    form.value = {
      enabled: d.enabled,
      imap_host: d.imap_host,
      imap_port: d.imap_port,
      imap_use_ssl: d.imap_use_ssl,
      imap_username: d.imap_username,
      imap_password: null, // write-only: никогда не предзаполняем
      imap_folder: d.imap_folder,
      poll_interval_seconds: d.poll_interval_seconds,
      expected_interval_days: d.expected_interval_days,
      notify_emails: d.notify_emails,
      poll_enabled: d.poll_enabled,
      mail_subject_filter: d.mail_subject_filter,
      mail_sender_filter: d.mail_sender_filter,
      mail_attachment_filter: d.mail_attachment_filter,
    }
    passwordSet.value = d.imap_password_set
    notifyEmailsStr.value = (d.notify_emails ?? []).join(', ')
    isDirty.value = false
  },
  { immediate: true },
)

// Dirty-tracking: любое изменение формы.
watch(form, () => { isDirty.value = true }, { deep: true })
watch(notifyEmailsStr, () => { isDirty.value = true })

const testing = ref(false)
const testResult = ref<ErpSyncTestResult | null>(null)

function buildDto(): ErpSyncSettingsIn {
  const f = form.value!
  const dto: ErpSyncSettingsIn = {
    enabled: f.enabled,
    imap_host: (f.imap_host || '').trim() || null,
    imap_port: f.imap_port ?? 993,
    imap_use_ssl: f.imap_use_ssl,
    imap_username: (f.imap_username || '').trim() || null,
    imap_folder: f.imap_folder || 'INBOX',
    poll_interval_seconds: f.poll_interval_seconds ?? 900,
    expected_interval_days: f.expected_interval_days ?? 4,
    notify_emails: notifyEmailsStr.value.trim()
      ? notifyEmailsStr.value.split(',').map((s) => s.trim()).filter(Boolean)
      : null,
    poll_enabled: f.poll_enabled,
    mail_subject_filter: (f.mail_subject_filter || '').trim() || null,
    mail_sender_filter: (f.mail_sender_filter || '').trim() || null,
    mail_attachment_filter: (f.mail_attachment_filter || '').trim() || null,
  }
  if (f.imap_password) {
    dto.imap_password = f.imap_password
  }
  return dto
}

async function onSave() {
  if (!form.value) return
  try {
    await putMut.mutateAsync(buildDto())
    message.success(t('common.saved'))
    form.value.imap_password = null
    isDirty.value = false
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}

async function onTest() {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await testErpSync()
  } catch (e) {
    testResult.value = { ok: false, error: parseApiError(e, t) }
  } finally {
    testing.value = false
  }
}
</script>

<style scoped>
@import '../admin-tabs.css';

.erp-sync__subtitle {
  margin: 20px 0 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}
.erp-sync__hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--color-text-secondary, #666);
}
.kb-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
@media (max-width: 720px) {
  .kb-grid { grid-template-columns: 1fr; }
}
</style>
