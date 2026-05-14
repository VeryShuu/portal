<template>
  <n-modal
    :show="show"
    preset="card"
    :title="t('kb.new_section')"
    style="max-width:420px"
    @update:show="$emit('update:show', $event)"
  >
    <n-form @submit.prevent="$emit('submit')">
      <n-form-item :label="t('kb.section.form.titleLabel')" required>
        <n-input
          :value="form.title"
          :placeholder="t('kb.section.form.titlePlaceholder')"
          @update:value="updateField('title', $event)"
        />
      </n-form-item>
      <n-form-item :label="t('kb.section.form.descriptionLabel')">
        <n-input
          :value="form.description"
          type="textarea"
          :rows="2"
          :placeholder="t('kb.section.form.descriptionPlaceholder')"
          @update:value="updateField('description', $event)"
        />
      </n-form-item>
      <div class="modal-actions">
        <n-button @click="$emit('update:show', false)">{{ t('common.cancel') }}</n-button>
        <n-button
          type="primary"
          :loading="saving"
          :disabled="!form.title.trim()"
          attr-type="submit"
        >{{ t('kb.section.create') }}</n-button>
      </div>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NModal, NForm, NFormItem, NInput, NButton } from 'naive-ui'

export interface KbSectionForm {
  title: string
  description: string
  parent_id: string | null
}

const props = defineProps<{
  show: boolean
  form: KbSectionForm
  saving: boolean
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
  (e: 'update:form', value: KbSectionForm): void
  (e: 'submit'): void
}>()

const { t } = useI18n()

function updateField(field: 'title' | 'description', value: string) {
  emit('update:form', { ...props.form, [field]: value })
}
</script>

<style scoped>
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
</style>
