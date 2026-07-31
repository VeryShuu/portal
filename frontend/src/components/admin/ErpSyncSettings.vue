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
import type { ErpSyncSettingsIn, ErpSyncSettingsOut } from '../../api/erpSync'
import { useErpSyncSettingsQuery, usePutErpSyncSettingsMutation } from '../../queries/erpSync'

const { t } = useI18n()
const message = useMessage()

const { data, isLoading } = useErpSyncSettingsQuery()
const putMut = usePutErpSyncSettingsMutation()

interface FormState {
  enabled: boolean
  poll_interval_seconds: number
  expected_interval_days: number
  notify_emails: string[] | null
  poll_enabled: boolean
  mail_subject_filter: string | null
  mail_sender_filter: string | null
  mail_attachment_filter: string | null
}

const form = ref<FormState | null>(null)
const isDirty = ref(false)
const notifyEmailsStr = ref('')

// Загрузка данных в форму.
watch(
  data,
  (d: ErpSyncSettingsOut | undefined) => {
    if (!d) return
    form.value = {
      enabled: d.enabled,
      poll_interval_seconds: d.poll_interval_seconds,
      expected_interval_days: d.expected_interval_days,
      notify_emails: d.notify_emails,
      poll_enabled: d.poll_enabled,
      mail_subject_filter: d.mail_subject_filter,
      mail_sender_filter: d.mail_sender_filter,
      mail_attachment_filter: d.mail_attachment_filter,
    }
    notifyEmailsStr.value = (d.notify_emails ?? []).join(', ')
    isDirty.value = false
  },
  { immediate: true },
)

// Dirty-tracking: любое изменение формы.
watch(form, () => { isDirty.value = true }, { deep: true })
watch(notifyEmailsStr, () => { isDirty.value = true })

function buildDto(): ErpSyncSettingsIn {
  const f = form.value!
  return {
    enabled: f.enabled,
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
}

async function onSave() {
  if (!form.value) return
  try {
    await putMut.mutateAsync(buildDto())
    message.success(t('common.saved'))
    isDirty.value = false
  } catch (e) {
    message.error(parseApiError(e, t))
  }
}
</script>

<style scoped>
@import '../../pages/admin/admin-tabs.css';

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
