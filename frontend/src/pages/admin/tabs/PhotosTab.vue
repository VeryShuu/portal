<template>
  <div class="branding-section">
    <div class="module-header">
      <div>
        <div class="branding-section__title">{{ t('admin.modules.photos.title') }}</div>
        <div class="branding-section__hint">{{ t('admin.modules.photos.hint') }}</div>
      </div>
      <n-switch v-model:value="photosForm.enabled" />
    </div>
    <template v-if="photosForm.enabled">
      <div class="branding-fields" style="margin-top:16px">
        <div class="email-row-2">
          <n-form-item :label="t('admin.modules.widgetLimit')" style="margin-bottom:0;max-width:200px">
            <n-input-number v-model:value="photosForm.widget_limit" :min="1" :max="50" />
          </n-form-item>
          <n-form-item :label="t('admin.modules.photos.maxSizeMb')" style="margin-bottom:0;max-width:200px">
            <n-input-number v-model:value="photosForm.max_size_mb" :min="1" :max="500" />
          </n-form-item>
        </div>
        <n-form-item :label="t('admin.modules.photos.allowedMime')" style="margin-bottom:0">
          <n-input
            v-model:value="photosForm.allowed_mime"
            :placeholder="t('admin.modules.photos.allowedMimePlaceholder')"
          />
        </n-form-item>
        <n-form-item style="margin-bottom:0">
          <n-checkbox v-model:checked="photosForm.strip_gps">
            {{ t('admin.modules.photos.stripGps') }}
          </n-checkbox>
        </n-form-item>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NSwitch, NInputNumber, NFormItem, NInput, NCheckbox } from 'naive-ui'

const { t } = useI18n()

interface PhotosForm {
  enabled: boolean
  widget_limit: number
  max_size_mb: number
  allowed_mime: string
  strip_gps: boolean
}

defineProps<{ photosForm: PhotosForm }>()
</script>

<style scoped>
</style>
