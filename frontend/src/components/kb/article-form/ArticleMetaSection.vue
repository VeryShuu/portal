<template>
  <n-form-item
    :label="t('kb.form.title')"
    required
    :validation-status="error ? 'error' : undefined"
    :feedback="error ? errorText : undefined"
  >
    <n-input
      ref="inputRef"
      :value="title"
      :placeholder="t('kb.form.titlePlaceholder')"
      size="large"
      class="title-input"
      @update:value="$emit('update:title', $event)"
    />
  </n-form-item>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { NFormItem, NInput, type InputInst } from 'naive-ui'

const props = defineProps<{
  title: string
  error?: boolean
  errorText?: string
  autofocus?: boolean
}>()

defineEmits<{
  'update:title': [value: string]
}>()

const { t } = useI18n()

const inputRef = ref<InputInst | null>(null)

onMounted(() => {
  if (props.autofocus && typeof inputRef.value?.focus === 'function') {
    inputRef.value.focus()
  }
})
</script>

<style scoped>
.title-input :deep(input) {
  font-size: 22px;
  font-weight: 700;
}
</style>
