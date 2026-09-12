<template>
  <section class="branding-section">
    <h3 class="branding-section__title">
      {{ t('admin.approvals.settings.title') }}
    </h3>
    <p class="branding-section__hint">
      {{ t('admin.approvals.settings.hint') }}
    </p>

    <n-spin :show="isLoading">
      <n-form
        v-if="form"
        label-placement="top"
        :show-feedback="false"
      >
        <div class="kb-grid">
          <n-form-item :label="t('admin.approvals.settings.baseUrl')">
            <n-input
              v-model:value="form.base_url"
              placeholder="https://erp.mage.ru/MageErp/hs/Auth"
            />
            <template #feedback>
              <span class="approvals__field-hint">{{ t('admin.approvals.settings.baseUrlHint') }}</span>
            </template>
          </n-form-item>
          <n-form-item :label="t('admin.approvals.settings.tokenBaseUrl')">
            <n-input
              v-model:value="form.token_base_url"
              :placeholder="t('admin.approvals.settings.tokenBaseUrlPlaceholder')"
            />
            <template #feedback>
              <span class="approvals__field-hint">{{ t('admin.approvals.settings.tokenBaseUrlHint') }}</span>
            </template>
          </n-form-item>
          <n-form-item :label="t('admin.approvals.settings.authUsername')">
            <n-input
              v-model:value="form.auth_username"
              placeholder="Portal"
            />
            <template #feedback>
              <span class="approvals__field-hint">{{ t('admin.approvals.settings.authUsernameHint') }}</span>
            </template>
          </n-form-item>
        </div>

        <div class="kb-grid">
          <n-form-item :label="t('admin.approvals.settings.authPassword')">
            <n-input
              v-model:value="form.auth_password"
              type="password"
              show-password-on="click"
              :placeholder="
                passwordSet
                  ? t('admin.approvals.settings.passwordKeep')
                  : t('admin.approvals.settings.passwordPlaceholder')
              "
              :input-props="{ autocomplete: 'new-password' }"
            />
          </n-form-item>
        </div>

        <div class="approvals__actions">
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
            {{ t('admin.approvals.settings.testConnection') }}
          </n-button>
          <div
            v-if="saveResult"
            class="approvals__save-result"
            :class="saveResult.ok ? 'approvals__save-result--ok' : 'approvals__save-result--fail'"
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
import { NButton, NForm, NFormItem, NInput, NSpin, useMessage } from 'naive-ui'
import { parseApiError } from '../../utils/parseApiError'
import { testApprovalsConnection } from '../../api/approvals'
import { useApprovalsSettingsQuery, usePutApprovalsSettingsMutation } from '../../queries/approvals'

const { t } = useI18n()
const message = useMessage()

const { data, isLoading } = useApprovalsSettingsQuery()
const putMut = usePutApprovalsSettingsMutation()

interface FormState {
  base_url: string
  token_base_url: string | null
  auth_username: string
  auth_password: string | null
}

const form = ref<FormState | null>(null)
const isDirty = ref(false)
const passwordSet = ref(false)
const testing = ref(false)
// Статический фидбэк (не пропадает через 3с, как useMessage-тост).
const saveResult = ref<{ ok: boolean; message: string } | null>(null)

watch(
  data,
  (d) => {
    if (!d) return
    form.value = {
      base_url: d.base_url,
      token_base_url: d.token_base_url || '',
      auth_username: d.auth_username,
      auth_password: null,
    }
    passwordSet.value = d.password_set
    isDirty.value = false
    saveResult.value = null
  },
  { immediate: true },
)

watch(
  form,
  () => {
    isDirty.value = true
    saveResult.value = null
  },
  { deep: true },
)

function buildDto() {
  const f = form.value!
  return {
    base_url: f.base_url.trim(),
    token_base_url: (f.token_base_url || '').trim(),
    auth_username: f.auth_username.trim(),
    ...(f.auth_password ? { auth_password: f.auth_password.trim() } : {}),
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

async function onTest() {
  testing.value = true
  saveResult.value = null
  try {
    const res = await testApprovalsConnection()
    if (res.ok) {
      saveResult.value = { ok: true, message: res.message }
      message.success(res.message)
    } else {
      const msg = res.message || t('admin.approvals.settings.testFail')
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

.approvals__field-hint {
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
  .kb-grid {
    grid-template-columns: 1fr;
  }
}
.approvals__actions {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border, #e5e7eb);
}
.approvals__save-result {
  font-size: 13px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: var(--radius-md, 8px);
}
.approvals__save-result--ok {
  color: #1a7f37;
  background: var(--color-success-bg, #dafbe1);
}
.approvals__save-result--fail {
  color: #cf222e;
  background: var(--color-danger-bg, #ffebe9);
}
</style>
