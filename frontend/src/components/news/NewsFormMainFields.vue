<template>
  <div class="form-card">
    <n-form-item
      :label="t('news.form.titleLabel')"
      path="title"
    >
      <n-input
        ref="titleInput"
        v-model:value="title"
        :placeholder="t('news.create.placeholder')"
        size="large"
      />
    </n-form-item>

    <n-form-item
      :label="t('news.form.bodyLabel')"
      path="body"
    >
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
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NFormItem, NInput, type InputInst } from 'naive-ui'
import RichEditor from '../RichEditor.vue'

const props = defineProps<{ uploadEndpoint?: string; autofocus?: boolean }>()

const title = defineModel<string>('title', { required: true })
const body = defineModel<string>('body', { required: true })

const { t } = useI18n()

const titleInput = ref<InputInst | null>(null)

onMounted(() => {
  if (props.autofocus && typeof titleInput.value?.focus === 'function') {
    titleInput.value.focus()
  }
})
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
