<template>
  <div class="branding-section">
    <div class="module-header">
      <div>
        <div class="branding-section__title">{{ t('admin.modules.photos.title') }}</div>
        <div class="branding-section__hint">{{ t('admin.modules.photos.hint') }}</div>
      </div>
      <n-switch v-model:value="localForm.enabled" />
    </div>
    <template v-if="localForm.enabled">
      <div class="branding-fields" style="margin-top:16px">
        <div class="email-row-2">
          <n-form-item :label="t('admin.modules.widgetLimit')" style="margin-bottom:0;max-width:200px">
            <n-input-number v-model:value="localForm.widget_limit" :min="1" :max="50" />
          </n-form-item>
          <n-form-item :label="t('admin.modules.photos.maxSizeMb')" style="margin-bottom:0;max-width:200px">
            <n-input-number v-model:value="localForm.max_size_mb" :min="1" :max="500" />
          </n-form-item>
        </div>
        <n-form-item :label="t('admin.modules.photos.allowedMime')" style="margin-bottom:0">
          <n-input
            v-model:value="localForm.allowed_mime"
            :placeholder="t('admin.modules.photos.allowedMimePlaceholder')"
          />
        </n-form-item>
        <n-form-item style="margin-bottom:0">
          <n-checkbox v-model:checked="localForm.strip_gps">
            {{ t('admin.modules.photos.stripGps') }}
          </n-checkbox>
        </n-form-item>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
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

const props = defineProps<{ photosForm: PhotosForm }>()
const emit = defineEmits<{ 'update:photosForm': [value: PhotosForm] }>()

const localForm = reactive<PhotosForm>({ ...props.photosForm })

watch(
  () => props.photosForm,
  (v) => { Object.assign(localForm, v) },
  { deep: true },
)

watch(localForm, () => {
  emit('update:photosForm', { ...localForm })
})
</script>

<style scoped>
</style>
