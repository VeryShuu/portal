<template>
  <n-modal
    :show="show"
    :title="t('files.folders.create')"
    preset="card"
    style="width: 480px"
    @update:show="$emit('update:show', $event)"
  >
    <n-form>
      <n-form-item :label="t('files.folders.name')">
        <n-input
          v-model:value="name"
          :placeholder="t('files.folders.namePlaceholder')"
        />
      </n-form-item>
      <n-form-item :label="t('files.folders.description')">
        <n-input
          v-model:value="description"
          type="textarea"
          :rows="2"
        />
      </n-form-item>
    </n-form>
    <template #footer>
      <div style="display: flex; gap: 8px; justify-content: flex-end">
        <n-button @click="$emit('update:show', false)">
          {{ t('common.cancel') }}
        </n-button>
        <n-button
          type="primary"
          :loading="loading"
          @click="onSubmit"
        >
          {{ t('common.create') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NForm, NFormItem, NInput, NModal } from 'naive-ui'

const props = defineProps<{
  show: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  submit: [payload: { name: string; description: string | null }]
}>()

const { t } = useI18n()

const name = ref('')
const description = ref('')

watch(() => props.show, (val) => {
  if (!val) {
    name.value = ''
    description.value = ''
  }
})

function onSubmit() {
  if (!name.value.trim()) return
  emit('submit', { name: name.value.trim(), description: description.value || null })
}
</script>
