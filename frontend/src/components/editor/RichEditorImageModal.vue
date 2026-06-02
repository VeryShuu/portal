<template>
  <n-modal
    v-model:show="show"
    preset="dialog"
    :title="t('editor.image.dialogTitle')"
    style="max-width: 480px"
  >
    <div class="link-form">
      <div
        v-if="src"
        class="image-preview"
      >
        <img
          :src="src"
          :alt="alt || ''"
        >
      </div>
      <div class="link-field">
        <!-- eslint-disable-next-line vuejs-accessibility/label-has-for -->
        <label
          class="link-label"
          for="image-alt-input"
        >{{ t('editor.image.alt') }}</label>
        <n-input
          v-model:value="alt"
          :placeholder="t('editor.image.altPlaceholder')"
          :input-props="{ id: 'image-alt-input' }"
          clearable
        />
      </div>
      <div class="link-field">
        <!-- eslint-disable-next-line vuejs-accessibility/label-has-for -->
        <label
          class="link-label"
          for="image-caption-input"
        >{{ t('editor.image.caption') }}</label>
        <n-input
          v-model:value="caption"
          type="textarea"
          :rows="2"
          :placeholder="t('editor.image.captionPlaceholder')"
          :input-props="{ id: 'image-caption-input' }"
          clearable
        />
      </div>
    </div>
    <template #action>
      <n-button
        size="small"
        @click="$emit('cancel')"
      >
        {{ t('common.cancel') }}
      </n-button>
      <n-button
        size="small"
        type="primary"
        :disabled="!src"
        @click="$emit('submit')"
      >
        {{ t('editor.insert') }}
      </n-button>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { NButton, NInput, NModal } from 'naive-ui'
import { useI18n } from 'vue-i18n'

const show = defineModel<boolean>('show', { required: true })
const alt = defineModel<string>('alt', { required: true })
const caption = defineModel<string>('caption', { required: true })

defineProps<{
  src: string
}>()

defineEmits<{
  submit: []
  cancel: []
}>()

const { t } = useI18n()
</script>

<style scoped>
.link-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}
.link-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.link-label {
  font-size: 13px;
  color: var(--n-text-color-2, #666);
}
.image-preview {
  display: flex;
  justify-content: center;
  margin-bottom: 4px;
}
.image-preview img {
  max-width: 100%;
  max-height: 200px;
  border-radius: 4px;
  border: 1px solid var(--n-border-color, #e0e0e6);
}
</style>
