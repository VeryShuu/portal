<template>
  <section class="branding-section">
    <h3 class="branding-section__title">
      {{ t('admin.directum.settings.title') }}
    </h3>
    <p class="branding-section__hint">
      {{ t('admin.directum.settings.hint') }}
    </p>

    <n-spin :show="isLoading">
      <n-form
        v-if="form"
        label-placement="top"
        :show-feedback="false"
      >
        <!-- ── Общие настройки ─────────────────────────────────────────── -->
        <h4 class="directum__subtitle">
          {{ t('admin.directum.settings.commonTitle') }}
        </h4>
        <p class="directum__hint">
          {{ t('admin.directum.settings.commonHint') }}
        </p>

        <div class="erp-toggle-row">
          <n-switch v-model:value="form.enabled" />
          <div class="erp-toggle-row__label">
            <span class="erp-toggle-row__title">{{ t('admin.directum.settings.enabled') }}</span>
            <span class="directum__field-hint">{{ t('admin.directum.settings.enabledHint') }}</span>
          </div>
        </div>

        <div class="kb-grid">
          <n-form-item :label="t('admin.directum.settings.baseUrl')">
            <n-input
              v-model:value="form.base_url"
              placeholder="https://sed.mage.ru/Integration/odata"
            />
            <template #feedback>
              <span class="directum__field-hint">{{ t('admin.directum.settings.baseUrlHint') }}</span>
            </template>
          </n-form-item>
          <n-form-item :label="t('admin.directum.settings.authUsername')">
            <n-input
              v-model:value="form.auth_username"
              placeholder="PDC1\portal-directum"
            />
            <template #feedback>
              <span class="directum__field-hint">{{ t('admin.directum.settings.authUsernameHint') }}</span>
            </template>
          </n-form-item>
        </div>

        <div class="kb-grid">
          <n-form-item :label="t('admin.directum.settings.authPassword')">
            <n-input
              v-model:value="form.auth_password"
              type="password"
              show-password-on="click"
              :placeholder="
                passwordSet
                  ? t('admin.directum.settings.passwordKeep')
                  : t('admin.directum.settings.passwordPlaceholder')
              "
              :input-props="{ autocomplete: 'new-password' }"
            />
          </n-form-item>
        </div>

        <div class="kb-grid">
          <n-form-item :label="t('admin.directum.settings.expectedInterval')">
            <n-input-number
              v-model:value="form.expected_interval_days"
              :min="1"
              :max="30"
              style="width: 100%"
            />
            <template #feedback>
              <span class="directum__field-hint">{{ t('admin.directum.settings.expectedIntervalHint') }}</span>
            </template>
          </n-form-item>
          <n-form-item :label="t('admin.directum.settings.notifyEmails')">
            <n-input
              v-model:value="notifyEmailsStr"
              :placeholder="t('admin.directum.settings.notifyEmailsPlaceholder')"
            />
            <template #feedback>
              <span class="directum__field-hint">{{ t('admin.directum.settings.notifyEmailsHint') }}</span>
            </template>
          </n-form-item>
        </div>

        <!-- ── Задача: Просроченные задачи ──────────────────────────────── -->
        <h4 class="directum__subtitle">
          {{ t('admin.directum.settings.overdueTitle') }}
        </h4>
        <p class="directum__hint">
          {{ t('admin.directum.settings.overdueHint') }}
        </p>

        <div class="erp-toggle-row">
          <n-switch v-model:value="form.overdue_enabled" />
          <div class="erp-toggle-row__label">
            <span class="erp-toggle-row__title">{{ t('admin.directum.settings.overdueEnabled') }}</span>
            <span class="directum__field-hint">{{ t('admin.directum.settings.overdueEnabledHint') }}</span>
          </div>
        </div>

        <n-form-item :label="t('admin.directum.settings.runHours')">
          <n-select
            v-model:value="form.overdue_run_hours"
            multiple
            clearable
            :options="runHourOptions"
            :placeholder="t('admin.directum.settings.runHoursPlaceholder')"
          />
          <template #feedback>
            <span class="directum__field-hint">{{ t('admin.directum.settings.runHoursHint') }}</span>
          </template>
        </n-form-item>

        <!-- ── Действия ────────────────────────────────────────────────── -->
        <div class="directum__actions">
          <n-button
            type="primary"
            :loading="putMut.isPending.value"
            :disabled="!isDirty || putMut.isPending.value"
            @click="onSave"
          >
            {{ t('common.save') }}
          </n-button>
          <n-button
            :loading="testing"
            :disabled="isDirty"
            @click="onTest"
          >
            {{ t('admin.directum.settings.testConnection') }}
          </n-button>
          <div
            v-if="saveResult"
            class="directum__save-result"
            :class="saveResult.ok ? 'directum__save-result--ok' : 'directum__save-result--fail'"
          >
            {{ saveResult.message }}
          </div>
        </div>
      </n-form>
    </n-spin>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NForm, NFormItem, NInput, NInputNumber, NSelect, NSpin, NSwitch, useMessage } from 'naive-ui'
import { parseApiError } from '../../utils/parseApiError'
import {
  testDirectumConnection,
  type DirectumSettingsIn,
  type DirectumSettingsOut,
} from '../../api/directum'
import { useDirectumSettingsQuery, usePutDirectumSettingsMutation } from '../../queries/directum'

const { t } = useI18n()
const message = useMessage()

const { data, isLoading } = useDirectumSettingsQuery()
const putMut = usePutDirectumSettingsMutation()

interface FormState {
  enabled: boolean
  base_url: string
  auth_username: string | null
  auth_password: string | null
  overdue_run_hours: number[]
  expected_interval_days: number
  notify_emails: string[] | null
  overdue_enabled: boolean
}

const form = ref<FormState | null>(null)
const isDirty = ref(false)
const passwordSet = ref(false)
const notifyEmailsStr = ref('')
const testing = ref(false)
// Статический фидбэк (не пропадает через 3с, как useMessage-тост).
const saveResult = ref<{ ok: boolean; message: string } | null>(null)

// Опции «часов запуска» 00:00–23:00 (московское время).
const runHourOptions = Array.from({ length: 24 }, (_, h) => ({
  label: `${String(h).padStart(2, '0')}:00`,
  value: h,
}))

watch(
  data,
  (d: DirectumSettingsOut | undefined) => {
    if (!d) return
    form.value = {
      enabled: d.enabled,
      base_url: d.base_url,
      auth_username: d.auth_username,
      auth_password: null,
      overdue_run_hours: [...(d.overdue_run_hours ?? [])],
      expected_interval_days: d.expected_interval_days,
      notify_emails: d.notify_emails,
      overdue_enabled: d.overdue_enabled,
    }
    passwordSet.value = d.password_set
    notifyEmailsStr.value = (d.notify_emails ?? []).join(', ')
    isDirty.value = false
    saveResult.value = null
  },
  { immediate: true },
)

watch(form, () => {
  isDirty.value = true
  saveResult.value = null
}, { deep: true })
watch(notifyEmailsStr, () => {
  isDirty.value = true
  saveResult.value = null
})

const canEnable = computed(() => {
  const f = form.value
  if (!f) return true
  return Boolean(
    f.base_url.trim() && (f.auth_username || '').trim() && (f.auth_password || passwordSet.value),
  )
})

function buildDto(): DirectumSettingsIn {
  const f = form.value!
  return {
    enabled: f.enabled,
    base_url: f.base_url.trim(),
    auth_username: (f.auth_username || '').trim() || null,
    ...(f.auth_password ? { auth_password: f.auth_password } : {}),
    overdue_run_hours: [...f.overdue_run_hours].sort((a, b) => a - b),
    expected_interval_days: f.expected_interval_days ?? 2,
    notify_emails: notifyEmailsStr.value.trim()
      ? notifyEmailsStr.value.split(',').map((s) => s.trim()).filter(Boolean)
      : null,
    overdue_enabled: f.overdue_enabled,
  }
}

async function onSave() {
  if (!form.value) return
  if (form.value.enabled && !canEnable.value) {
    const msg = t('admin.directum.settings.enableRequiresCreds')
    saveResult.value = { ok: false, message: msg }
    message.error(msg)
    return
  }
  // Включённая задача без часов расписания никогда бы не запускалась —
  // ловим локально (бэкенд дублирует 400).
  if (form.value.overdue_enabled && form.value.overdue_run_hours.length === 0) {
    const msg = t('admin.directum.settings.enableRequiresHours')
    saveResult.value = { ok: false, message: msg }
    message.error(msg)
    return
  }
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

async function onTest() {
  testing.value = true
  saveResult.value = null
  try {
    const res = await testDirectumConnection()
    if (res.ok) {
      saveResult.value = { ok: true, message: res.detail ?? t('admin.directum.settings.testOk') }
      message.success(t('admin.directum.settings.testOk'))
    } else {
      const msg = res.error ?? t('admin.directum.settings.testFail')
      saveResult.value = { ok: false, message: msg }
      message.error(msg)
    }
  } catch (e) {
    const msg = parseApiError(e, t)
    saveResult.value = { ok: false, message: msg }
    message.error(msg)
  } finally {
    testing.value = false
  }
}
</script>

<style scoped>
@import '../../pages/admin/admin-tabs.css';

.directum__subtitle {
  margin: 24px 0 4px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border, #e5e7eb);
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text);
}
.directum__subtitle:first-of-type {
  border-top: none;
  padding-top: 0;
  margin-top: 12px;
}
.directum__hint {
  margin: 0 0 14px;
  font-size: 12px;
  color: var(--color-text-secondary, #666);
  line-height: 1.5;
}
.directum__field-hint {
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

/* Строка «переключатель + подпись» (как в ErpSyncSettings). */
.erp-toggle-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}
.erp-toggle-row :deep(.n-switch) {
  flex-shrink: 0;
  margin-top: 2px;
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

.directum__actions {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border, #e5e7eb);
}
.directum__save-result {
  font-size: 13px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: var(--radius-md, 8px);
}
.directum__save-result--ok {
  color: #1a7f37;
  background: var(--color-success-bg, #dafbe1);
}
.directum__save-result--fail {
  color: #cf222e;
  background: var(--color-danger-bg, #ffebe9);
}
</style>
