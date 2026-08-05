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
        <!-- ── Общие настройки ─────────────────────────────────────────── -->
        <h4 class="erp-sync__subtitle">
          {{ t('admin.erpSync.settings.commonTitle') }}
        </h4>
        <p class="erp-sync__hint">
          {{ t('admin.erpSync.settings.commonHint') }}
        </p>

        <div class="erp-toggle-row">
          <n-switch v-model:value="form.enabled" />
          <div class="erp-toggle-row__label">
            <span class="erp-toggle-row__title">{{ t('admin.erpSync.settings.enabled') }}</span>
          </div>
        </div>

        <div class="kb-grid">
          <n-form-item :label="t('admin.erpSync.settings.pollInterval')">
            <n-input-number
              v-model:value="form.poll_interval_seconds"
              :min="60"
              :max="3600"
              style="width: 100%"
            />
            <template #feedback>
              <span class="erp-sync__field-hint">{{ t('admin.erpSync.settings.pollIntervalHint') }}</span>
            </template>
          </n-form-item>
          <n-form-item :label="t('admin.erpSync.settings.notifyEmails')">
            <n-input
              v-model:value="notifyEmailsStr"
              :placeholder="t('admin.erpSync.settings.notifyEmailsPlaceholder')"
            />
            <template #feedback>
              <span class="erp-sync__field-hint">{{ t('admin.erpSync.settings.notifyEmailsHint') }}</span>
            </template>
          </n-form-item>
        </div>

        <div class="erp-toggle-row">
          <n-switch v-model:value="form.delete_after_fetch" />
          <div class="erp-toggle-row__label">
            <span class="erp-toggle-row__title">{{ t('admin.erpSync.settings.deleteAfterFetch') }}</span>
            <span class="erp-sync__field-hint">{{ t('admin.erpSync.settings.deleteAfterFetchHint') }}</span>
          </div>
        </div>

        <!-- ── Дни рождения ────────────────────────────────────────────── -->
        <h4 class="erp-sync__subtitle">
          {{ t('admin.erpSync.settings.filtersTitle') }}
        </h4>
        <p class="erp-sync__hint">
          {{ t('admin.erpSync.settings.filtersHint') }}
        </p>

        <div class="erp-toggle-row">
          <n-switch v-model:value="form.poll_enabled" />
          <div class="erp-toggle-row__label">
            <span class="erp-toggle-row__title">{{ t('admin.erpSync.settings.pollEnabled') }}</span>
            <span class="erp-sync__field-hint">{{ t('admin.erpSync.settings.pollEnabledHint') }}</span>
          </div>
        </div>

        <div class="kb-grid">
          <n-form-item :label="t('admin.erpSync.settings.expectedInterval')">
            <n-input-number
              v-model:value="form.expected_interval_days"
              :min="1"
              :max="30"
              style="width: 100%"
            />
            <template #feedback>
              <span class="erp-sync__field-hint">{{ t('admin.erpSync.settings.expectedIntervalHint') }}</span>
            </template>
          </n-form-item>
        </div>

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
        </div>

        <!-- ── Отсутствия ──────────────────────────────────────────────── -->
        <h4 class="erp-sync__subtitle">
          {{ t('admin.erpSync.settings.absencesTitle') }}
        </h4>
        <p class="erp-sync__hint">
          {{ t('admin.erpSync.settings.absencesHint') }}
        </p>

        <div class="erp-toggle-row">
          <n-switch v-model:value="form.absences_poll_enabled" />
          <div class="erp-toggle-row__label">
            <span class="erp-toggle-row__title">{{ t('admin.erpSync.settings.absencesPollEnabled') }}</span>
            <span class="erp-sync__field-hint">{{ t('admin.erpSync.settings.absencesPollEnabledHint') }}</span>
          </div>
        </div>

        <div class="kb-grid">
          <n-form-item :label="t('admin.erpSync.settings.absencesExpectedInterval')">
            <n-input-number
              v-model:value="form.absences_expected_interval_days"
              :min="1"
              :max="30"
              style="width: 100%"
            />
            <template #feedback>
              <span class="erp-sync__field-hint">{{ t('admin.erpSync.settings.expectedIntervalHint') }}</span>
            </template>
          </n-form-item>
        </div>

        <div class="kb-grid">
          <n-form-item :label="t('admin.erpSync.settings.absencesSubjectFilter')">
            <n-input
              v-model:value="form.mail_absences_subject_filter"
              :placeholder="t('admin.erpSync.settings.absencesSubjectFilterPlaceholder')"
            />
          </n-form-item>
          <n-form-item :label="t('admin.erpSync.settings.absencesSenderFilter')">
            <n-input
              v-model:value="form.mail_absences_sender_filter"
              placeholder="erp@company.local"
            />
          </n-form-item>
          <n-form-item :label="t('admin.erpSync.settings.absencesAttachmentFilter')">
            <n-input
              v-model:value="form.mail_absences_attachment_filter"
              placeholder=".txt"
            />
          </n-form-item>
        </div>

        <!-- ── Действия ────────────────────────────────────────────────── -->
        <div class="erp-sync__actions">
          <n-button
            type="primary"
            :loading="putMut.isPending.value"
            :disabled="!isDirty || putMut.isPending.value"
            @click="onSave"
          >
            {{ t('common.save') }}
          </n-button>
          <div
            v-if="saveResult"
            class="erp-sync__save-result"
            :class="saveResult.ok ? 'erp-sync__save-result--ok' : 'erp-sync__save-result--fail'"
          >
            {{ saveResult.message }}
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
  delete_after_fetch: boolean
  absences_poll_enabled: boolean
  mail_absences_subject_filter: string | null
  mail_absences_sender_filter: string | null
  mail_absences_attachment_filter: string | null
  absences_expected_interval_days: number
}

const form = ref<FormState | null>(null)
const isDirty = ref(false)
const notifyEmailsStr = ref('')
// Статический фидбэк сохранения (не пропадает через 3с, как useMessage-тост).
const saveResult = ref<{ ok: boolean; message: string } | null>(null)

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
      delete_after_fetch: d.delete_after_fetch,
      absences_poll_enabled: d.absences_poll_enabled,
      mail_absences_subject_filter: d.mail_absences_subject_filter,
      mail_absences_sender_filter: d.mail_absences_sender_filter,
      mail_absences_attachment_filter: d.mail_absences_attachment_filter,
      absences_expected_interval_days: d.absences_expected_interval_days,
    }
    notifyEmailsStr.value = (d.notify_emails ?? []).join(', ')
    isDirty.value = false
    saveResult.value = null
  },
  { immediate: true },
)

// Dirty-tracking: любое изменение формы + сброс фидбэка при правках.
watch(form, () => {
  isDirty.value = true
  saveResult.value = null
}, { deep: true })
watch(notifyEmailsStr, () => {
  isDirty.value = true
  saveResult.value = null
})

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
    delete_after_fetch: f.delete_after_fetch,
    absences_poll_enabled: f.absences_poll_enabled,
    mail_absences_subject_filter: (f.mail_absences_subject_filter || '').trim() || null,
    mail_absences_sender_filter: (f.mail_absences_sender_filter || '').trim() || null,
    mail_absences_attachment_filter: (f.mail_absences_attachment_filter || '').trim() || null,
    absences_expected_interval_days: f.absences_expected_interval_days ?? 7,
  }
}

async function onSave() {
  if (!form.value) return
  saveResult.value = null
  try {
    await putMut.mutateAsync(buildDto())
    isDirty.value = false
    saveResult.value = { ok: true, message: t('common.saved') }
    message.success(t('common.saved'))
  } catch (e) {
    const msg = parseApiError(e, t)
    saveResult.value = { ok: false, message: msg }
    message.error(msg)
  }
}
</script>

<style scoped>
@import '../../pages/admin/admin-tabs.css';

.erp-sync__subtitle {
  margin: 24px 0 4px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border, #e5e7eb);
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text);
}
.erp-sync__subtitle:first-of-type {
  border-top: none;
  padding-top: 0;
  margin-top: 12px;
}
.erp-sync__hint {
  margin: 0 0 14px;
  font-size: 12px;
  color: var(--color-text-secondary, #666);
  line-height: 1.5;
}
.erp-sync__field-hint {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: var(--color-text-secondary, #888);
  line-height: 1.4;
}
.kb-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 14px;
}
@media (max-width: 720px) {
  .kb-grid { grid-template-columns: 1fr; }
}

/* Строка «переключатель + подпись» — flex с выравниванием по верхнему краю,
   переключатель固定-ширины слева, текст справа переносится. */
.erp-toggle-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}
.erp-toggle-row :deep(.n-switch) {
  flex-shrink: 0;
  margin-top: 2px;  /* визуально центрировать относительно первой строки текста */
}
.erp-toggle-row__label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.erp-toggle-row__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  line-height: 1.4;
}

.erp-sync__actions {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border, #e5e7eb);
}
.erp-sync__save-result {
  font-size: 13px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: var(--radius-md, 8px);
}
.erp-sync__save-result--ok {
  color: #1a7f37;
  background: var(--color-success-bg, #dafbe1);
}
.erp-sync__save-result--fail {
  color: #cf222e;
  background: var(--color-danger-bg, #ffebe9);
}
</style>
