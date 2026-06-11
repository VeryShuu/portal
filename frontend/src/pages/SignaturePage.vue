<template>
  <div class="signature-page">
    <div class="signature-page__head">
      <h1 class="signature-page__title">
        {{ t('signature.title') }}
      </h1>
      <n-button
        v-if="auth.isAdmin"
        size="tiny"
        quaternary
        circle
        :title="t('signature.admin.openSettings')"
        @click="manage.open('module')"
      >
        <template #icon>
          <n-icon :component="SettingsOutline" />
        </template>
      </n-button>
    </div>
    <p class="signature-page__subtitle">
      {{ t('signature.subtitle') }}
    </p>

    <div class="signature-page__grid">
      <n-card class="signature-page__form-card">
        <n-form
          label-placement="top"
          @submit.prevent="generate"
        >
          <div class="signature-row-2">
            <n-form-item
              :label="t('signature.fields.name')"
              :feedback="nameError"
              :validation-status="nameError ? 'error' : undefined"
            >
              <n-input
                v-model:value="form.name"
                :maxlength="20"
                :placeholder="t('signature.fields.namePlaceholder')"
              />
            </n-form-item>
            <n-form-item
              :label="t('signature.fields.surname')"
              :feedback="surnameError"
              :validation-status="surnameError ? 'error' : undefined"
            >
              <n-input
                v-model:value="form.surname"
                :maxlength="20"
                :placeholder="t('signature.fields.surnamePlaceholder')"
              />
            </n-form-item>
          </div>

          <n-form-item :label="t('signature.fields.position')">
            <n-input
              v-model:value="form.position"
              :maxlength="150"
              :placeholder="t('signature.fields.positionPlaceholder')"
            />
          </n-form-item>

          <div class="signature-row-2">
            <n-form-item :label="t('signature.fields.language')">
              <n-select
                v-model:value="form.language"
                :options="languageOptions"
              />
            </n-form-item>
            <n-form-item :label="t('signature.fields.device')">
              <n-select
                v-model:value="form.device"
                :options="deviceOptions"
              />
            </n-form-item>
          </div>

          <n-form-item :label="t('signature.fields.city')">
            <n-select
              v-model:value="form.cityId"
              :options="cityOptions"
              :placeholder="t('signature.fields.cityPlaceholder')"
            />
          </n-form-item>

          <div class="signature-row-2">
            <n-form-item :label="t('signature.fields.officePhone')">
              <n-select
                v-model:value="form.officePhone"
                :options="officePhoneOptions"
                clearable
                :placeholder="t('signature.fields.officePhonePlaceholder')"
              />
            </n-form-item>
            <n-form-item
              :label="t('signature.fields.extension')"
              :feedback="extensionError"
              :validation-status="extensionError ? 'error' : undefined"
            >
              <n-input
                :value="form.extension"
                :maxlength="3"
                :placeholder="t('signature.fields.extensionPlaceholder')"
                @update:value="onExtensionInput"
              />
            </n-form-item>
          </div>

          <n-form-item :label="t('signature.fields.mobile')">
            <n-input
              :value="form.mobilePhone"
              :placeholder="t('signature.fields.mobilePlaceholder')"
              @update:value="onMobileInput"
            />
          </n-form-item>

          <n-form-item
            :label="t('signature.fields.email')"
            :feedback="emailError"
            :validation-status="emailError ? 'error' : undefined"
          >
            <n-input
              v-model:value="form.email"
              :placeholder="t('signature.fields.emailPlaceholder', { domain: emailDomain })"
            />
          </n-form-item>

          <SignatureActions
            :can-generate="isValid"
            :generating="generating"
            :generated="generated"
            :has-result="!!previewHtml"
            :mailto-support="mailtoSupport"
            :support-email="supportEmail"
            @generate="generate"
            @copy="onCopy"
            @download="downloadHtm"
          />
        </n-form>
      </n-card>

      <n-card class="signature-page__preview-card">
        <SignaturePreview :html="previewHtml" />
      </n-card>
    </div>

    <n-drawer
      v-if="auth.isAdmin"
      :show="manage.is('module')"
      :width="640"
      placement="right"
      :on-update:show="(v: boolean) => { if (!v) manage.close() }"
    >
      <n-drawer-content
        :title="t('signature.admin.openSettings')"
        closable
      >
        <Suspense>
          <SignatureModuleSettings />
        </Suspense>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NCard,
  NDrawer,
  NDrawerContent,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NSelect,
  useMessage,
} from 'naive-ui'
import { SettingsOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../stores/auth'
import { useManageDrawer } from '../composables/useManageDrawer'
import { useSignatureForm } from './composables/useSignatureForm'
import SignaturePreview from '../components/signature/SignaturePreview.vue'
import SignatureActions from '../components/signature/SignatureActions.vue'

const { t } = useI18n()
const auth = useAuthStore()
const message = useMessage()
const manage = useManageDrawer(['module'])

const SignatureModuleSettings = defineAsyncComponent(
  () => import('../components/admin/SignatureModuleSettings.vue'),
)

const {
  form,
  cityOptions,
  officePhoneOptions,
  languageOptions,
  deviceOptions,
  supportEmail,
  mailtoSupport,
  emailDomain,
  previewHtml,
  generating,
  generated,
  isValid,
  generate,
  onMobileInput,
  onExtensionInput,
  copyHtml,
  downloadHtm,
} = useSignatureForm()

const nameError = computed(() =>
  form.name && form.name.trim().length > 20 ? t('signature.errors.tooLong', { max: 20 }) : '',
)
const surnameError = computed(() =>
  form.surname && form.surname.trim().length > 20 ? t('signature.errors.tooLong', { max: 20 }) : '',
)
const extensionError = computed(() =>
  form.extension && !/^[0-9]{3}$/.test(form.extension) ? t('signature.errors.extension') : '',
)
const emailError = computed(() => {
  const email = form.email.trim().toLowerCase()
  if (!email) return ''
  return email.endsWith('@' + emailDomain.value)
    ? ''
    : t('signature.errors.emailDomain', { domain: emailDomain.value })
})

async function onCopy() {
  const ok = await copyHtml()
  if (ok) message.success(t('signature.actions.copied'))
  else message.error(t('errors.generic'))
}
</script>

<style scoped>
.signature-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 16px;
}
.signature-page__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.signature-page__title {
  font-size: 22px;
  font-weight: 600;
  margin: 0;
}
.signature-page__subtitle {
  color: var(--color-text-secondary, #666);
  font-size: 13px;
  margin: 4px 0 16px;
}
.signature-page__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.signature-row-2 {
  display: flex;
  gap: 12px;
}
.signature-row-2 > * {
  flex: 1;
}
@media (max-width: 860px) {
  .signature-page__grid {
    grid-template-columns: 1fr;
  }
}
</style>
