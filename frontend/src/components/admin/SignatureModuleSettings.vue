<template>
  <div class="signature-module-settings">
    <div
      v-if="!modulesData?.signature?.enabled"
      class="module-disabled-hint"
    >
      {{ t('admin.modules.signature.disabledHint') }}
    </div>

    <template v-else>
      <section class="settings-section">
        <h4 class="settings-section__title">
          {{ t('admin.modules.signature.generalTitle') }}
        </h4>
        <n-form-item :label="t('admin.modules.signature.supportEmail')">
          <n-input
            v-model:value="form.support_email"
            placeholder="it@mage.ru"
          />
        </n-form-item>
        <n-form-item :label="t('admin.modules.signature.companyUrl')">
          <n-input
            v-model:value="form.company_url"
            placeholder="http://mage.ru/"
          />
        </n-form-item>
        <n-form-item :label="t('admin.modules.signature.logoBaseUrl')">
          <n-input
            v-model:value="form.logo_base_url"
            placeholder="http://mage.ru/signature/images/"
          />
          <template #feedback>
            {{ t('admin.modules.signature.logoBaseUrlHint') }}
          </template>
        </n-form-item>
      </section>

      <section class="settings-section">
        <h4 class="settings-section__title">
          {{ t('admin.modules.signature.officePhones') }}
        </h4>
        <n-dynamic-input
          v-model:value="form.office_phones"
          :min="1"
          :placeholder="t('admin.modules.signature.officePhonePlaceholder')"
          @create="() => ''"
        />
      </section>

      <section class="settings-section">
        <h4 class="settings-section__title">
          {{ t('admin.modules.signature.cities') }}
        </h4>
        <n-dynamic-input
          v-model:value="form.cities"
          :min="1"
          :on-create="createCity"
        >
          <template #default="{ value }">
            <div class="signature-city-row">
              <n-input
                v-model:value="value.label_ru"
                :placeholder="t('admin.modules.signature.cityLabelRu')"
              />
              <n-input
                v-model:value="value.label_eng"
                :placeholder="t('admin.modules.signature.cityLabelEng')"
              />
              <n-input
                v-model:value="value.suffix_ru"
                :placeholder="t('admin.modules.signature.citySuffixRu')"
              />
              <n-input
                v-model:value="value.suffix_eng"
                :placeholder="t('admin.modules.signature.citySuffixEng')"
              />
            </div>
          </template>
        </n-dynamic-input>
      </section>

      <div class="settings-actions">
        <n-button
          type="primary"
          :loading="saving"
          @click="onSave"
        >
          {{ t('common.save') }}
        </n-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NDynamicInput,
  NFormItem,
  NInput,
  useMessage,
} from 'naive-ui'
import { useModulesAdminQuery } from '../../queries/admin'
import {
  useSignatureSettingsQuery,
  useUpdateSignatureSettingsMutation,
} from '../../queries/signature'
import type { SignatureCity, SignatureSettings } from '../../api/signature'

const { t } = useI18n()
const message = useMessage()

const { data: modulesData } = useModulesAdminQuery()
const moduleEnabled = ref(false)
watch(modulesData, (d) => { moduleEnabled.value = !!d?.signature?.enabled }, { immediate: true })

const { data: settingsData } = useSignatureSettingsQuery({ enabled: moduleEnabled })
const updateMutation = useUpdateSignatureSettingsMutation()

const form = reactive<SignatureSettings>({
  cities: [],
  office_phones: [],
  support_email: 'it@mage.ru',
  company_url: 'http://mage.ru/',
  logo_base_url: 'http://mage.ru/signature/images/',
})
const saving = ref(false)

watch(settingsData, (data) => {
  if (!data) return
  form.cities = data.cities.map((c) => ({ ...c }))
  form.office_phones = [...data.office_phones]
  form.support_email = data.support_email
  form.company_url = data.company_url
  form.logo_base_url = data.logo_base_url
}, { immediate: true })

let nextId = -1
function createCity(): SignatureCity {
  return { id: nextId--, label_ru: '', label_eng: '', suffix_ru: '', suffix_eng: '' }
}

async function onSave() {
  saving.value = true
  try {
    await updateMutation.mutateAsync({
      cities: form.cities,
      office_phones: form.office_phones.filter((p) => p.trim()),
      support_email: form.support_email.trim(),
      company_url: form.company_url.trim(),
      logo_base_url: form.logo_base_url.trim(),
    })
    message.success(t('admin.modules.saved'))
  } catch {
    message.error(t('errors.generic'))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.signature-module-settings {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.settings-section__title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
}
.signature-city-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  width: 100%;
}
.settings-actions {
  display: flex;
  justify-content: flex-end;
}
.module-disabled-hint {
  color: var(--color-text-muted, #999);
  font-size: 13px;
}
</style>
