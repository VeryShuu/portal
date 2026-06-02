<template>
  <div class="form-card">
    <n-form-item
      :label="t('news.form.titleLabel')"
      path="title"
    >
      <n-input
        v-model:value="title"
        :placeholder="t('news.create.placeholder')"
        size="large"
      />
    </n-form-item>

    <n-form-item :label="t('news.form.bodyLabel')">
      <RichEditor
        v-model="body"
        :placeholder="t('news.create.bodyPlaceholder')"
        :upload-endpoint="uploadEndpoint"
        style="width:100%"
      />
    </n-form-item>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NFormItem, NInput } from 'naive-ui'
import RichEditor from '../RichEditor.vue'

defineProps<{ uploadEndpoint?: string }>()

const title = defineModel<string>('title', { required: true })
const body = defineModel<string>('body', { required: true })

const { t } = useI18n()
</script>

<style scoped>
.form-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px 22px;
  box-shadow: var(--shadow-sm);
  transition: border-color 0.15s, box-shadow 0.15s;
}
</style>
