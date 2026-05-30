<template>
  <n-form-item
    v-if="!isEdit"
    :label="t('meetings.form.recurrence')"
  >
    <RecurrenceEditor
      v-model="form.recurrence"
      :start-date="startDateStr"
      :max-days="maxRecurrenceDays"
    />
  </n-form-item>

  <template v-if="isEdit && hasSeries">
    <n-form-item :label="t('meetings.form.applyTo')">
      <n-radio-group v-model:value="form.apply_to">
        <n-space>
          <n-radio value="this">
            {{ t('meetings.form.applyToThis') }}
          </n-radio>
          <n-radio value="series">
            {{ t('meetings.form.applyToSeries') }}
          </n-radio>
        </n-space>
      </n-radio-group>
    </n-form-item>
  </template>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { NFormItem, NRadioGroup, NRadio, NSpace } from 'naive-ui'
import RecurrenceEditor from '../RecurrenceEditor.vue'
import type { FormState } from './composables/useMeetingFormState'

defineProps<{
  form: FormState
  isEdit: boolean
  hasSeries: boolean
  startDateStr: string
  maxRecurrenceDays: number
}>()

const { t } = useI18n()
</script>
