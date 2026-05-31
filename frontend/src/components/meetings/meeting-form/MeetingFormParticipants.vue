<template>
  <n-form-item :label="t('meetings.form.participants')">
    <ParticipantPicker
      v-model="form.invited_users"
      :min-chars="minSearchChars"
    />
  </n-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NFormItem } from 'naive-ui'
import ParticipantPicker from '../ParticipantPicker.vue'
import type { FormState } from './composables/useMeetingFormState'

defineModel<FormState>('form', { required: true })
defineProps<{
  minSearchChars: number
}>()

const { t } = useI18n()
</script>
