<template>
  <div class="branding-wrap">
    <div class="branding-section">
      <div class="branding-section__title">{{ t('admin.email.serverTitle') }}</div>
      <div class="branding-section__hint">{{ t('admin.email.serverHint') }}</div>
      <div class="branding-fields">
        <div class="email-row-2">
          <n-form-item :label="t('admin.email.host')" style="margin-bottom:0;flex:1">
            <n-input v-model:value="emailForm.host" :placeholder="t('admin.email.hostPlaceholder')" />
          </n-form-item>
          <n-form-item :label="t('admin.email.port')" style="margin-bottom:0;width:110px">
            <n-input-number v-model:value="emailForm.port" :min="1" :max="65535" style="width:100%" />
          </n-form-item>
        </div>
        <n-form-item :label="t('admin.email.fromAddress')" style="margin-bottom:0">
          <n-input v-model:value="emailForm.from_address" :placeholder="t('admin.email.fromAddressPlaceholder')" />
        </n-form-item>
        <div class="email-row-2">
          <n-form-item :label="t('admin.email.username')" style="margin-bottom:0;flex:1">
            <n-input v-model:value="emailForm.username" :placeholder="t('admin.email.usernamePlaceholder')" clearable />
          </n-form-item>
          <n-form-item :label="t('admin.email.password')" style="margin-bottom:0;flex:1">
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
        <n-form-item :label="t('admin.email.encryption')" style="margin-bottom:0">
          <div class="email-switches">
            <n-switch v-model:value="emailForm.use_tls" @update:value="v => { if (v) emailForm.use_starttls = false }">
              <template #checked>TLS</template>
              <template #unchecked>TLS</template>
            </n-switch>
            <span class="email-switch-label">TLS</span>
            <n-switch v-model:value="emailForm.use_starttls" @update:value="v => { if (v) emailForm.use_tls = false }">
              <template #checked>STARTTLS</template>
              <template #unchecked>STARTTLS</template>
            </n-switch>
            <span class="email-switch-label">STARTTLS</span>
          </div>
        </n-form-item>
      </div>
      <div class="email-actions">
        <n-button type="primary" :loading="emailSaving" @click="saveEmailSettings">
          {{ t('common.save') }}
        </n-button>
        <n-button :loading="emailTesting" @click="openTestEmailModal">
          {{ t('admin.email.sendTest') }}
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
        <n-input v-model:value="testEmailAddress" :placeholder="t('admin.email.testToPlaceholder')" />
      </n-form-item>
      <template #footer>
        <div class="modal-footer">
          <n-button @click="testEmailModalOpen = false">{{ t('common.cancel') }}</n-button>
          <n-button type="primary" :loading="emailTesting" @click="sendTestEmail">
            {{ t('admin.email.sendTestBtn') }}
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NInput, NInputNumber, NFormItem, NSwitch, NModal, useMessage } from 'naive-ui'
import { api } from '../../../api'

const { t } = useI18n()
const message = useMessage()

interface EmailFormType {
  host: string
  port: number
  from_address: string
  username: string
  password: string
  use_tls: boolean
  use_starttls: boolean
}

const emailForm = ref<EmailFormType>({
  host: '',
  port: 25,
  from_address: '',
  username: '',
  password: '',
  use_tls: false,
  use_starttls: false,
})
const emailPasswordSet = ref(false)
const emailSaving = ref(false)
const emailTesting = ref(false)
const testEmailModalOpen = ref(false)
const testEmailAddress = ref('')
const emailLoadError = ref(false)

async function loadEmailSettings() {
  try {
    const data = await api<{
      host: string; port: number; from_address: string; username: string
      password_set: boolean; use_tls: boolean; use_starttls: boolean
    }>('/admin/email-settings')
    emailForm.value = {
      host: data.host,
      port: data.port,
      from_address: data.from_address,
      username: data.username,
      password: '',
      use_tls: data.use_tls,
      use_starttls: data.use_starttls,
    }
    emailPasswordSet.value = data.password_set
    emailLoadError.value = false
  } catch {
    emailLoadError.value = true
    message.error(t('errors.generic'))
  }
}

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
    }
    const data = await api<{ host: string; port: number; from_address: string; username: string; password_set: boolean; use_tls: boolean; use_starttls: boolean }>(
      '/admin/email-settings',
      { method: 'PUT', body: payload },
    )
    emailPasswordSet.value = data.password_set
    emailForm.value.password = ''
    message.success(t('admin.email.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    emailSaving.value = false
  }
}

function openTestEmailModal() {
  testEmailModalOpen.value = true
}

async function sendTestEmail() {
  if (!testEmailAddress.value.trim()) {
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
  } catch {
    message.error(t('errors.generic'))
  } finally {
    emailTesting.value = false
  }
}

onMounted(() => {
  void loadEmailSettings()
})
</script>

<style scoped>
@import '../admin-tabs.css';
</style>
